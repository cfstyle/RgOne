from __future__ import annotations
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 搜索路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

import pytest
from fastapi.testclient import TestClient
from backend.app.core.config import Settings, settings
from backend.app.core.security import (
    encrypt_secret,
    decrypt_secret,
    mask_name,
    mask_key,
    hash_password,
    verify_password,
)
from backend.app.main import app
from backend.app.services.new_api_client import NewApiClient, new_api_client


def test_security_utils():
    # 1. 姓名脱敏
    assert mask_name("张三") == "张*"
    assert mask_name("李晓明") == "李*明"
    assert mask_name("欧阳六六") == "欧**六"
    assert mask_name("陈") == "陈"

    # 2. Key 掩码
    raw_k = "sk-rgone1234567890abcdef"
    masked_k = mask_key(raw_k)
    assert masked_k.startswith("sk-rgo")
    assert masked_k.endswith("cdef")
    assert "..." in masked_k

    # 3. 对称加解密
    secret_text = "sk-super-secret-production-key-999"
    encrypted = encrypt_secret(secret_text)
    assert encrypted != secret_text
    decrypted = decrypt_secret(encrypted)
    assert decrypted == secret_text

    # 4. 密码哈希
    pwd = "Admin@RgOne2026"
    h = hash_password(pwd)
    assert verify_password(pwd, h) is True
    assert verify_password("WrongPassword", h) is False


def test_new_api_client_mock():
    import asyncio

    async def _test():
        # 连通性测试
        conn = await new_api_client.test_connection()
        assert conn["success"] is True

        # 拉取模型
        models = await new_api_client.list_models()
        assert len(models) >= 4
        ids = [m["id"] for m in models]
        assert "DeepSeek-V4-Flash-0731-INT8" in ids

        # 创建 Token
        token_info = await new_api_client.create_token("EMP_999999_测试")
        assert token_info["name"] == "EMP_999999_测试"
        assert token_info["key"].startswith("sk-")

        # 消费日志拉取
        logs = await new_api_client.fetch_consumption_logs(start_timestamp=0)
        assert isinstance(logs, list)

    asyncio.run(_test())


def test_employee_lookup(client: TestClient):
    # 查询存在的示范工号 001024
    resp = client.post("/api/v1/auth/emp/lookup", json={"emp_no": "001024"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["emp_no"] == "001024"
    assert data["department"] == "金融科技部 · 核心架构组"
    assert data["masked_name"] == "陈*"
    assert "陈飞" not in resp.text  # 绝不可返回真实全名

    # 查询不存在的工号
    resp_none = client.post("/api/v1/auth/emp/lookup", json={"emp_no": "999999"})
    assert resp_none.status_code == 404


def test_employee_verify_disabled_and_unified_login_flow(client: TestClient, monkeypatch):
    """
    验收要求：
    1. 生产环境已彻底关闭工号+姓名签发凭证的能力，返回 403 Forbidden；
    2. 统一工号+小秘书验证码登录，成功建立员工会话并自动申领 Key；
    3. 自主重置 Key 正常运转；
    4. 登录与 Key 申领解耦：网关故障时允许登录建立会话，进入系统后显示 pending_claim，并通过 POST /me/token/claim 免码补领成功。
    """
    import re
    import httpx

    captured_codes = []

    async def mock_post(self, url, *args, **kwargs):
        if "mock-xiaomishu" in str(url) or "xiaomishu" in str(url):
            json_body = kwargs.get("json", {})
            content = json_body.get("content", "")
            m = re.search(r"验证码为:\s*(\d{6})", content)
            if m:
                captured_codes.append(m.group(1))
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/json"},
                json={"errcode": 0, "errmsg": "ok", "success": True}
            )
        return httpx.Response(status_code=404)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # 1. 验证工号+姓名签发凭证已彻底下线（返回 403 Forbidden）
    resp_verify_disabled = client.post("/api/v1/auth/emp/verify", json={"emp_no": "001024", "name": "陈飞"})
    assert resp_verify_disabled.status_code == 403
    assert "已停用" in resp_verify_disabled.json()["detail"]

    # 2. 统一登录：获取验证码 -> 登录签发员工 JWT
    resp_send = client.post("/api/v1/auth/send-code", json={"account": "001024"})
    assert resp_send.status_code == 200, resp_send.text
    assert len(captured_codes) >= 1
    code = captured_codes[-1]

    resp_login = client.post("/api/v1/auth/login", json={"account": "001024", "code": code})
    assert resp_login.status_code == 200, resp_login.text
    auth_data = resp_login.json()
    assert auth_data["user_type"] == "employee"
    assert "access_token" in auth_data
    token = auth_data["access_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # 3. 访问个人工作台获取 Token 详情与配置
    resp_token = client.get("/api/v1/me/token", headers=headers)
    assert resp_token.status_code == 200, resp_token.text
    token_detail = resp_token.json()
    assert token_detail["emp_no"] == "001024"
    assert token_detail["name"] == "陈飞"
    assert token_detail["api_key"].startswith("sk-")
    assert token_detail["provider_id"] == "new-api-1"
    assert token_detail["base_url"].endswith("/v1")

    # 4. 自主重置 Token
    old_key = token_detail["api_key"]
    resp_reset = client.post("/api/v1/me/token/reset", headers=headers)
    assert resp_reset.status_code == 200, resp_reset.text
    reset_detail = resp_reset.json()
    assert reset_detail["reset_count"] >= 1
    assert reset_detail["api_key"] != old_key
    assert reset_detail["api_key"].startswith("sk-")

    # 5. 解耦断言：员工登录时网关故障，登录依然成功，进入系统后通过 /me/token/claim 补领成功
    new_emp_no = "06700956"
    resp_send_new = client.post("/api/v1/auth/send-code", json={"account": new_emp_no})
    assert resp_send_new.status_code == 200
    code_new = captured_codes[-1]

    # 模拟网关在登录瞬间故障
    new_api_client._mock_fail_create = True
    try:
        resp_login_gw_fail = client.post("/api/v1/auth/login", json={"account": new_emp_no, "code": code_new})
        # 即使网关异常，登录依然成功下发 JWT 会话！
        assert resp_login_gw_fail.status_code == 200
        new_token = resp_login_gw_fail.json()["access_token"]
        new_headers = {"Authorization": f"Bearer {new_token}"}

        # 此时读取 Token 为待申领态
        resp_pending = client.get("/api/v1/me/token", headers=new_headers)
        assert resp_pending.status_code == 200
        assert resp_pending.json()["status"] == "pending_claim"
    finally:
        new_api_client._mock_fail_create = False

    # 网关恢复后，使用当前已登录会话免验证码直接补领 Key
    resp_claim = client.post("/api/v1/me/token/claim", headers=new_headers)
    assert resp_claim.status_code == 200
    claim_detail = resp_claim.json()
    assert claim_detail["status"] == "active"
    assert claim_detail["api_key"].startswith("sk-")


def test_admin_flow(client: TestClient, monkeypatch):
    import re
    import httpx

    captured_codes = []

    async def mock_post(self, url, *args, **kwargs):
        if "mock-xiaomishu" in str(url) or "xiaomishu" in str(url):
            json_body = kwargs.get("json", {})
            content = json_body.get("content", "")
            m = re.search(r"验证码为:\s*(\d{6})", content)
            if m:
                captured_codes.append(m.group(1))
            return httpx.Response(status_code=200, json={"errcode": 0, "errmsg": "ok", "success": True})
        return httpx.Response(status_code=404)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # 1. 预先确保员工 001024 已有 Key
    client.post("/api/v1/auth/send-code", json={"account": "001024"})
    if captured_codes:
        client.post("/api/v1/auth/login", json={"account": "001024", "code": captured_codes[-1]})

    # 2. 管理员登录
    resp_login = client.post("/api/v1/auth/admin/login", json={
        "username": settings.INIT_ADMIN_USERNAME,
        "password": settings.INIT_ADMIN_PASSWORD,
    })
    assert resp_login.status_code == 200, resp_login.text
    admin_token = resp_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. 访问管理员总览
    resp_overview = client.get("/api/v1/admin/overview", headers=admin_headers)
    assert resp_overview.status_code == 200
    ov_data = resp_overview.json()["data"]
    assert ov_data["total_employees"] >= 3
    assert ov_data["claimed_tokens"] >= 1

    # 4. 读取设置
    resp_settings = client.get("/api/v1/admin/settings", headers=admin_headers)
    assert resp_settings.status_code == 200
    s_data = resp_settings.json()["data"]
    assert "new_api_base_url" in s_data
    assert "default_provider_id" in s_data

    # 5. 更新设置
    resp_update = client.put("/api/v1/admin/settings", json={
        "default_provider_name": "总行统一大模型中台"
    }, headers=admin_headers)
    assert resp_update.status_code == 200

    # 6. 测试网关连通性
    resp_test_gw = client.post("/api/v1/admin/test-gateway", json={"access_token": ""}, headers=admin_headers)
    assert resp_test_gw.status_code == 200
    assert resp_test_gw.json()["success"] is False
    assert resp_test_gw.json()["mock"] is False


def test_deployment_modes_isolate_mock_gateway_and_storage(monkeypatch, tmp_path):
    import asyncio

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "MOCK_NEW_API", True)
    gateway = NewApiClient(base_url="http://gateway.example.test", access_token="", mock=True)
    assert gateway.is_mock is False
    assert asyncio.run(gateway.test_connection())["success"] is False
    with pytest.raises(RuntimeError, match="未配置 new-api Access Token"):
        asyncio.run(gateway.fetch_consumption_logs(start_timestamp=0))

    monkeypatch.setattr(settings, "APP_ENV", "test")
    gateway = NewApiClient(base_url="http://gateway.example.test", access_token="configured")
    assert gateway.is_mock is True
    assert asyncio.run(gateway.fetch_consumption_logs(start_timestamp=0))
    assert NewApiClient(mock=False).is_mock is False

    production = Settings(APP_ENV="production", DEPLOYMENT_DATA_DIR=tmp_path)
    test = Settings(APP_ENV="test", DEPLOYMENT_DATA_DIR=tmp_path)
    assert production.resolved_database_url == f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
    assert test.resolved_database_url == f"sqlite:///{(tmp_path / 'test' / 'app.db').as_posix()}"
    assert production.resolved_downloads_dir == tmp_path / "storage" / "downloads"
    assert test.resolved_downloads_dir == tmp_path / "test" / "storage" / "downloads"
    assert test.resolved_images_dir == tmp_path / "test" / "storage" / "images"


def test_admin_gateway_probe_uses_real_request(client: TestClient, monkeypatch):
    import httpx
    from backend.app.core.security import create_access_token

    class GatewayTransport:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers):
            assert url == "http://gateway.example.test/api/user/self"
            assert headers["New-Api-User"] == "17"
            return httpx.Response(200, json={"success": True})

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "MOCK_NEW_API", True)
    monkeypatch.setattr(httpx, "AsyncClient", GatewayTransport)
    token = create_access_token({"sub": settings.INIT_ADMIN_USERNAME, "role": "admin"})
    response = client.post(
        "/api/v1/admin/test-gateway",
        json={"base_url": "http://gateway.example.test", "access_token": "gateway-fixture", "user_id": 17},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["mock"] is False


def test_guide_endpoints(client: TestClient):
    # 模型列表
    resp_m = client.get("/api/v1/guide/models")
    assert resp_m.status_code == 200
    assert resp_m.json()["total"] >= 4

    # 网关状态
    resp_s = client.get("/api/v1/guide/status")
    assert resp_s.status_code == 200
    assert resp_s.json()["gateway_connected"] is True

    # 主推安装包（新库默认停止生成 43 字节占位包，故初始为 False，无真实包不推荐）
    resp_inst = client.get("/api/v1/guide/recommended-installer")
    assert resp_inst.status_code == 200
    assert resp_inst.json()["has_installer"] is False


def test_production_clean_init_and_no_overwrite_employee():
    """
    验收要求 P1:
    - 验证生产模式全新数据库初始化后，绝不自动注入示范员工账号（记录数为 0）
    - 验证管理员录入维护的员工姓名，系统重启再次执行 init_database() 后严格保持原值，不被改写
    """
    import tempfile
    import shutil
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import backend.app.core.database as core_db
    import backend.app.services.init_db as init_db_mod
    from backend.app.models.employee import Employee

    tmpdir = tempfile.mkdtemp(prefix="rgone_clean_prod_test_")
    db_file = Path(tmpdir) / "prod_clean.db"

    try:
        engine_clean = create_engine(f"sqlite:///{db_file}", future=True)
        SessionClean = sessionmaker(bind=engine_clean, future=True)

        orig_engine = init_db_mod.engine
        orig_session = init_db_mod.SessionLocal

        init_db_mod.engine = engine_clean
        init_db_mod.SessionLocal = SessionClean

        try:
            # 1. 首次全新初始化
            init_db_mod.init_database()

            # 断言全新生产数据库中没有任何示范员工
            with SessionClean() as session:
                emp_count = session.query(Employee).count()
                assert emp_count == 0, f"生产模式初始化后员工白名单应为空，实际有 {emp_count} 条"

                # 2. 管理员手工录入/维护真实员工姓名
                session.add(Employee(
                    emp_no="06700956",
                    name="生产真实维护姓名_杜绝改写",
                    department="金融市场部",
                    phone_last4="0956",
                    is_active=True
                ))
                session.commit()

            # 3. 模拟系统重启，再次执行 init_database()
            init_db_mod.init_database()

            # 断言员工姓名与属性严格保持原值，绝未被种子覆盖
            with SessionClean() as session:
                emp = session.query(Employee).filter(Employee.emp_no == "06700956").first()
                assert emp is not None
                assert emp.name == "生产真实维护姓名_杜绝改写", f"员工姓名被非法改写为: {emp.name}"
                assert emp.department == "金融市场部"
        finally:
            init_db_mod.engine = orig_engine
            init_db_mod.SessionLocal = orig_session
            engine_clean.dispose()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main(["-v", __file__])
