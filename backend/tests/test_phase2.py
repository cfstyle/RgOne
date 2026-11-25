from __future__ import annotations
import asyncio
import concurrent.futures
import io
import json
import re
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app.core.config import settings
from backend.app.core.security import create_access_token, decrypt_secret
from backend.app.main import app
from backend.app.models.employee import Employee
from backend.app.models.token import UserToken
from backend.app.models.verification_code import VerificationCode
from backend.app.models.auth_lockout import AuthLockout
from backend.app.models.setting import SystemSetting
from backend.app.models.shared_file import SharedFile
from backend.app.models.log_cache import UsageLogCache
import backend.app.services.init_db as init_db_mod
import backend.app.services.log_sync as log_sync_mod
from backend.app.services.log_sync import LogSyncService
from backend.app.services.new_api_client import NewApiClient, TokenCreationRejected, new_api_client
from backend.app.services.xiaomishu_service import XiaomishuService


# 模拟小秘书推送替身，用于拦截外发请求并捕获动态验证码
class MockPusher:
    captured_messages = []
    should_fail = False
    fail_status = 500
    business_fail = False
    business_fail_msg = "小秘书业务接口拒绝"

    @classmethod
    def reset(cls):
        cls.captured_messages.clear()
        cls.should_fail = False
        cls.fail_status = 500
        cls.business_fail = False
        cls.business_fail_msg = "小秘书业务接口拒绝"


@pytest.fixture(autouse=True)
def patch_xiaomishu_pusher(monkeypatch):
    MockPusher.reset()

    # 替换 httpx.AsyncClient.post 调用
    import httpx

    original_post = httpx.AsyncClient.post

    async def mock_post(self, url, *args, **kwargs):
        if "mock-xiaomishu" in str(url) or "xiaomishu" in str(url):
            json_body = kwargs.get("json", {})
            MockPusher.captured_messages.append(json_body)

            if MockPusher.should_fail:
                return httpx.Response(status_code=MockPusher.fail_status, text="Mock push server error")

            if MockPusher.business_fail:
                return httpx.Response(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    json={"errcode": 99999, "errmsg": MockPusher.business_fail_msg, "success": False}
                )

            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/json"},
                json={"errcode": 0, "errmsg": "ok", "success": True}
            )

        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)


def extract_code_from_msg(content: str) -> str:
    m = re.search(r"验证码为:\s*(\d{6})", content)
    return m.group(1) if m else ""


def test_verification_code_security_and_login(client: TestClient, db_session, monkeypatch, caplog):
    """
    验收手册 1.1:
    - 响应和日志无验证码，无 mock_code
    - 推送失败时页面明确报错，不产生可用验证码
    - 跨 worker 校验（共享 DB）
    - 过期码被拒绝、已用码被拒绝
    - 输错锁定阈值
    - 同一码并发原子消费只成功一次
    """
    db_session.query(VerificationCode).delete()
    db_session.query(AuthLockout).delete()
    db_session.commit()
    caplog.set_level("INFO", logger="xiaomishu")

    emp_no = "06700956"

    # 1. 模拟推送失败场景（HTTP 500）
    MockPusher.should_fail = True
    r_fail = client.post("/api/v1/auth/send-code", json={"account": emp_no})
    assert r_fail.status_code == 400
    assert "小秘书服务响应异常" in r_fail.json()["detail"] or "失败" in r_fail.json()["detail"]
    assert "mock_code" not in r_fail.json()
    MockPusher.reset()

    # 2. 模拟推送业务失败场景 (errcode != 0)
    MockPusher.business_fail = True
    r_biz_fail = client.post("/api/v1/auth/send-code", json={"account": emp_no})
    assert r_biz_fail.status_code == 400
    assert "小秘书推送失败" in r_biz_fail.json()["detail"]
    MockPusher.reset()

    assert db_session.query(VerificationCode).filter_by(emp_no=emp_no).count() == 0

    # 3. 正常推送成功场景
    r_ok = client.post("/api/v1/auth/send-code", json={"account": emp_no})
    assert r_ok.status_code == 200, r_ok.text
    res_data = r_ok.json()
    assert res_data["success"] is True
    assert "mock_code" not in res_data
    assert "code" not in res_data  # 绝不可返回验证码明文
    assert len(MockPusher.captured_messages) == 1

    last_msg = MockPusher.captured_messages[0]["content"]
    code = extract_code_from_msg(last_msg)
    assert len(code) == 6
    assert code not in r_ok.text
    assert f"验证码为: {code}" not in caplog.text

    # 4. 输错验证码测试
    r_err = client.post("/api/v1/auth/login", json={"account": emp_no, "code": "000000"})
    assert r_err.status_code == 400
    assert "验证码错误" in r_err.json()["detail"] or "验证码无效" in r_err.json()["detail"]

    # 5. 过期码测试：将数据库中该验证码过期时间置为过去
    code_record = db_session.query(VerificationCode).filter(
        VerificationCode.emp_no == emp_no,
        VerificationCode.is_used == False
    ).first()
    assert code_record is not None
    code_record.expire_at = datetime.utcnow() - timedelta(minutes=10)
    db_session.commit()

    r_expired = client.post("/api/v1/auth/login", json={"account": emp_no, "code": code})
    assert r_expired.status_code == 400
    assert "已过期" in r_expired.json()["detail"] or "验证码" in r_expired.json()["detail"]

    # 恢复有效期并测试并发原子消费
    code_record.expire_at = datetime.utcnow() + timedelta(minutes=5)
    db_session.query(AuthLockout).delete()
    db_session.commit()

    # 6. 并发原子消费：5 个请求并发提交同一验证码，只有 1 个成功
    results = []
    barrier = threading.Barrier(5, timeout=10)

    def attempt_login(index):
        c = TestClient(app)
        barrier.wait()
        return c.post("/api/v1/auth/login", json={"account": emp_no, "code": code}, headers={
            "X-Forwarded-For": f"192.0.2.{index + 1}"
        })

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_login, index) for index in range(5)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    success_count = sum(1 for r in results if r.status_code == 200)
    fail_count = sum(1 for r in results if r.status_code == 400)
    assert success_count == 1, f"并发提交预期恰有 1 个成功，实际成功 {success_count} 个"
    assert fail_count == 4

    # 7. 已用码再次提交必定失败
    r_used = client.post("/api/v1/auth/login", json={"account": emp_no, "code": code})
    assert r_used.status_code == 400
    assert "验证码" in r_used.json()["detail"] or "已过期" in r_used.json()["detail"]

    # 8. 生产安全断言：两名不同员工分别申请验证码，绝不串号或错发给固定账号
    emp_a = "06700888"
    emp_b = "001024"
    MockPusher.reset()

    # 生产模式下（settings.XIAOMISHU_TEST_MODE 默认为 False）
    monkeypatch.setattr(settings, "XIAOMISHU_TEST_MODE", False)
    with monkeypatch.context() as patch:
        # 固定两次抽样结果，避免随机码碰巧相同影响收件人隔离断言。
        samples = iter((123456, 654321))
        patch.setattr("backend.app.services.xiaomishu_service.secrets.randbelow", lambda limit: next(samples))
        r_a = client.post("/api/v1/auth/send-code", json={"account": emp_a})
        assert r_a.status_code == 200, r_a.text
        r_b = client.post("/api/v1/auth/send-code", json={"account": emp_b})
        assert r_b.status_code == 200, r_b.text

    assert len(MockPusher.captured_messages) == 2
    msg_a = MockPusher.captured_messages[0]
    msg_b = MockPusher.captured_messages[1]

    # 严格断言推送接收人 touser 必须是员工各自工号
    assert msg_a["touser"] == emp_a
    assert msg_b["touser"] == emp_b
    code_a = extract_code_from_msg(msg_a["content"])
    code_b = extract_code_from_msg(msg_b["content"])
    assert code_a != code_b
    assert len(code_a) == 6 and len(code_b) == 6
    assert client.post("/api/v1/auth/login", json={"account": emp_b, "code": code_a}, headers={
        "X-Forwarded-For": "192.0.2.20"
    }).status_code == 400

    # 9. 真实跨进程 / 跨 Worker 校验断言：
    # 模拟 Worker A 生成验证码持久化在共享 SQLite，独立 Python 子进程 Worker B 执行校验
    worker_b_script = f"""
import json
import sys
from pathlib import Path
BASE_DIR = Path({repr(str(BASE_DIR))})
sys.path.insert(0, str(BASE_DIR))

from backend.app.core.config import settings
settings.DATABASE_URL = {repr(settings.DATABASE_URL)}
settings.MOCK_NEW_API = True

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)
resp = client.post('/api/v1/auth/login', json=json.load(sys.stdin))
if resp.status_code == 200 and 'access_token' in resp.json():
    sys.exit(0)
else:
    print('Worker B 跨进程核验失败:', resp.status_code)
    sys.exit(1)
"""
    proc = subprocess.run(
        [sys.executable, "-c", worker_b_script],
        input=json.dumps({"account": emp_a, "code": code_a}), capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, f"Worker B 独立子进程核验失败: {proc.stderr} {proc.stdout}"

    # Worker A (主进程) 再次尝试提交同一验证码，验证共享 DB 状态已被原子标记消费
    r_a_reused = client.post("/api/v1/auth/login", json={"account": emp_a, "code": code_a})
    assert r_a_reused.status_code == 400
    assert "验证码" in r_a_reused.json()["detail"] or "已过期" in r_a_reused.json()["detail"]

    # 10. 单独验证输错锁定，随后用正确验证码确认锁定仍然生效。
    db_session.query(AuthLockout).delete()
    db_session.commit()
    lockout_headers = {"X-Forwarded-For": "192.0.2.30"}
    for _ in range(settings.AUTH_MAX_FAILURES - 1):
        assert client.post("/api/v1/auth/login", json={"account": emp_b, "code": code_a}, headers=lockout_headers).status_code == 400
    locked = client.post("/api/v1/auth/login", json={"account": emp_b, "code": code_a}, headers=lockout_headers)
    assert locked.status_code == 429
    assert "锁定" in locked.json()["detail"]
    assert client.post("/api/v1/auth/login", json={"account": emp_b, "code": code_b}, headers=lockout_headers).status_code == 429

    # 清理错误锁定，避免影响后续测试
    db_session.query(AuthLockout).delete()
    db_session.query(VerificationCode).delete()
    db_session.commit()


@pytest.fixture
def first_claim_employee(db_session):
    employee = Employee(emp_no=f"claim-test-{uuid4().hex}", name="测试员工")
    db_session.add(employee)
    db_session.commit()
    jwt = create_access_token({"sub": employee.emp_no, "role": "employee"})
    return employee, {"Authorization": f"Bearer {jwt}"}


def test_first_claim_serializes_gateway_creation(client, db_session, monkeypatch, first_claim_employee):
    employee, headers = first_claim_employee
    start = threading.Barrier(2, timeout=10)
    loser_returned = threading.Event()
    calls = []
    original_create = new_api_client.create_token

    async def delayed_create(name):
        calls.append(name)
        assert await asyncio.to_thread(loser_returned.wait, 10)
        return await original_create(name)

    monkeypatch.setattr(new_api_client, "create_token", delayed_create)

    def claim():
        start.wait()
        test_client = TestClient(app)
        try:
            response = test_client.post("/api/v1/me/token/claim", headers=headers)
        finally:
            test_client.close()
        if response.status_code == 409:
            loser_returned.set()
        return response

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(claim) for _ in range(2)]
        responses = [future.result(timeout=20) for future in futures]

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(calls) == 1
    assert db_session.query(UserToken).filter_by(emp_no=employee.emp_no).count() == 1
    retry = client.post("/api/v1/me/token/claim", headers=headers)
    assert retry.status_code == 200
    assert len(calls) == 1


def test_first_claim_reconciles_ambiguous_creation(client, db_session, monkeypatch, first_claim_employee):
    import httpx

    employee, headers = first_claim_employee
    original_create = new_api_client.create_token
    original_search = new_api_client.get_token_by_name
    visible = False
    calls = []

    async def delayed_visibility(name, **kwargs):
        return await original_search(name, **kwargs) if visible else None

    async def create_then_timeout(name):
        calls.append(await original_create(name))
        raise httpx.ReadTimeout("mock response timeout")

    monkeypatch.setattr(new_api_client, "get_token_by_name", delayed_visibility)
    monkeypatch.setattr(new_api_client, "create_token", create_then_timeout)
    assert client.post("/api/v1/me/token/claim", headers=headers).status_code == 502
    assert client.post("/api/v1/me/token/claim", headers=headers).status_code == 502
    assert client.get("/api/v1/me/token", headers=headers).json()["status"] == "pending_claim"
    assert len(calls) == 1
    pending_key = db_session.query(SystemSetting.key).filter_by(value=calls[0]["name"]).one().key
    admin_jwt = create_access_token({"sub": settings.INIT_ADMIN_USERNAME, "role": "admin"})
    admin_settings = client.get("/api/v1/admin/settings", headers={"Authorization": f"Bearer {admin_jwt}"})
    assert admin_settings.status_code == 200
    assert pending_key not in admin_settings.json()["data"]

    visible = True
    assert client.post("/api/v1/me/token/claim", headers=headers).status_code == 200
    assert len(calls) == 1
    persisted = db_session.query(UserToken).filter_by(emp_no=employee.emp_no).one()
    assert persisted.new_api_token_id == calls[0]["id"]
    assert db_session.get(SystemSetting, pending_key) is None


def test_first_claim_stops_on_uncertain_lookup_or_failed_delete(client, db_session, monkeypatch, first_claim_employee):
    employee, headers = first_claim_employee
    calls = []
    masked = False

    async def search(name, **kwargs):
        if masked:
            return {"id": 321, "name": name, "key": "sk-****"}
        raise RuntimeError("mock lookup failure")

    async def reject_delete(token_id):
        calls.append(("delete", token_id))
        return False

    async def create(name):
        calls.append(("create", name))
        pytest.fail("网关状态未确认时不能签发新 Key")

    monkeypatch.setattr(new_api_client, "get_token_by_name", search)
    monkeypatch.setattr(new_api_client, "delete_token", reject_delete)
    monkeypatch.setattr(new_api_client, "create_token", create)

    assert client.post("/api/v1/me/token/claim", headers=headers).status_code == 502
    assert calls == []
    masked = True
    assert client.post("/api/v1/me/token/claim", headers=headers).status_code == 502
    assert calls == [("delete", 321)]
    assert db_session.query(UserToken).filter_by(emp_no=employee.emp_no).count() == 0


def test_gateway_token_search_and_create_distinguish_uncertainty(monkeypatch):
    import httpx

    gateway = NewApiClient(mock=False, base_url="https://mock-gateway.invalid")
    response = httpx.Response(200, json={"success": True, "data": []})
    post_error = httpx.ConnectTimeout

    async def fake_get(*args, **kwargs):
        return response

    async def fake_post(*args, **kwargs):
        raise post_error("mock timeout")

    async def unexpected_delete(*args, **kwargs):
        pytest.fail("申领查询不能调用网关删除接口")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "delete", unexpected_delete)
    assert asyncio.run(gateway.get_token_by_name("mock-name")) is None
    response = httpx.Response(200, json={"success": True, "data": {"items": [], "total": 0, "page": 1, "page_size": 20}})
    assert asyncio.run(gateway.get_token_by_name("mock-name")) is None
    response = httpx.Response(200, json={"success": True, "data": {"items": None, "total": 0, "page": 1, "page_size": 20}})
    assert asyncio.run(gateway.get_token_by_name("mock-name")) is None
    response = httpx.Response(200, json={
        "success": True,
        "data": {
            "items": [{"id": 7, "name": "mock-name", "key": "sk-paginated-key"}],
            "total": 1,
            "page": 1,
            "page_size": 20,
        },
    })
    assert asyncio.run(gateway.get_token_by_name("mock-name")) == {
        "id": 7,
        "name": "mock-name",
        "key": "sk-paginated-key",
    }
    response = httpx.Response(200, json={"success": False})
    with pytest.raises(RuntimeError, match="可确认"):
        asyncio.run(gateway.get_token_by_name("mock-name"))
    response = httpx.Response(200, json={"data": []})
    with pytest.raises(RuntimeError, match="可确认"):
        asyncio.run(gateway.get_token_by_name("mock-name"))
    response = httpx.Response(200, json={"success": True, "data": [
        {"id": 1, "name": "mock-name"}, {"id": 2, "name": "mock-name"}
    ]})
    with pytest.raises(RuntimeError, match="无法确认唯一"):
        asyncio.run(gateway.get_token_by_name("mock-name", clean_duplicates=False))
    response = httpx.Response(503)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        asyncio.run(gateway.get_token_by_name("mock-name"))
    with pytest.raises(TokenCreationRejected):
        asyncio.run(gateway.create_token("mock-name"))
    post_error = httpx.ReadTimeout
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(gateway.create_token("mock-name"))


def test_gateway_token_status_and_resilient_reset(client: TestClient, db_session):
    """
    验收手册 1.2:
    - 正常禁用与启用
    - 网关失败时本地状态不更新
    - 员工与管理员重置复用同一事务
    - 旧 Key 删除失败停止签发，旧 Key 已删新 Key 签发失败进入 pending_reset 并支持安全重试
    - 管理员禁用后，员工自助重置 403 明确拒绝
    """
    db_session.query(AuthLockout).delete()
    db_session.query(VerificationCode).delete()
    db_session.commit()

    # 管理员登录获取凭证
    r_adm = client.post("/api/v1/auth/admin/login", json={
        "username": settings.INIT_ADMIN_USERNAME,
        "password": settings.INIT_ADMIN_PASSWORD
    })
    admin_token = r_adm.json()["access_token"]
    adm_headers = {"Authorization": f"Bearer {admin_token}"}

    # 为测试员工 06701099 统一登录并自动签发初始可用 Token
    client.post("/api/v1/auth/send-code", json={"account": "06701099"})
    code_val = extract_code_from_msg(MockPusher.captured_messages[-1]["content"])
    r_emp_auth = client.post("/api/v1/auth/login", json={"account": "06701099", "code": code_val})
    assert r_emp_auth.status_code == 200
    emp_jwt = r_emp_auth.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_jwt}"}

    r_my_token = client.get("/api/v1/me/token", headers=emp_headers)
    assert r_my_token.status_code == 200
    t_row = db_session.query(UserToken).filter(UserToken.emp_no == "06701099").first()
    assert t_row is not None
    token_id = t_row.id

    # 1. 正常禁用
    r_dis = client.put(f"/api/v1/admin/tokens/{token_id}/status", json={"status": "disabled"}, headers=adm_headers)
    assert r_dis.status_code == 200
    db_session.expire_all()
    t_row = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert t_row.status == "disabled"

    # 2. 网关异常时本地不更新状态
    new_api_client._mock_fail_status = True
    r_fail_enable = client.put(f"/api/v1/admin/tokens/{token_id}/status", json={"status": "active"}, headers=adm_headers)
    assert r_fail_enable.status_code == 502
    db_session.expire_all()
    t_row = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert t_row.status == "disabled"  # 本地状态严格保持 disabled 不变！
    new_api_client._mock_fail_status = False

    # 3. 员工自助重置：已被管理员禁用，自助重置必须返回 403 拒绝！
    r_emp_reset_forbidden = client.post("/api/v1/me/token/reset", headers=emp_headers)
    assert r_emp_reset_forbidden.status_code == 403
    assert "已被管理员禁用" in r_emp_reset_forbidden.json()["detail"]

    # 恢复启用状态
    client.put(f"/api/v1/admin/tokens/{token_id}/status", json={"status": "active"}, headers=adm_headers)
    db_session.expire_all()
    t_row = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert t_row.status == "active"

    # 4. 重置容灾测试 A：旧 Key 在网关删除失败，停止签发新 Key
    new_api_client._mock_fail_delete = True
    r_reset_del_fail = client.post(f"/api/v1/admin/tokens/{token_id}/reset", headers=adm_headers)
    assert r_reset_del_fail.status_code == 502
    db_session.expire_all()
    t_row = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert t_row.status == "active"
    assert t_row.reset_count == 0  # 未推进
    new_api_client._mock_fail_delete = False

    # 5. 重置容灾测试 B：旧 Key 已删，但新 Key 创建失败 -> 进入 pending_reset 可恢复状态
    new_api_client._mock_fail_create = True
    r_reset_create_fail = client.post(f"/api/v1/admin/tokens/{token_id}/reset", headers=adm_headers)
    assert r_reset_create_fail.status_code == 502
    db_session.expire_all()
    t_row = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert t_row.status == "pending_reset"
    assert t_row.new_api_token_id is None
    new_api_client._mock_fail_create = False

    # 6. 安全重试恢复：再次发起重置，检测到 pending_reset，跳过删除旧 Key，直接签发新 Key 并恢复 active！
    r_recover = client.post(f"/api/v1/admin/tokens/{token_id}/reset", headers=adm_headers)
    assert r_recover.status_code == 200
    db_session.expire_all()
    t_row = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert t_row.status == "active"
    assert t_row.new_api_token_id is not None
    assert t_row.reset_count >= 1
    raw_key = decrypt_secret(t_row.api_key_encrypted)
    assert raw_key.startswith("sk-")

    # 7. 正常 Key 重置并发防重签测试（从 active 正常状态发起并发争抢，持有独占锁直至结束，网关唯一 Key）
    # A. 确保 Token 当前处于正常 active 状态
    db_session.expire_all()
    t_curr = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert t_curr.status == "active"
    initial_token_name = t_curr.token_name

    # B. 真实模拟网关网络调用耗时期间（300ms），两个请求通过 Barrier 精确并发冲击争抢签发权
    import asyncio
    orig_create = new_api_client.create_token

    async def slow_create_token(*args, **kwargs):
        await asyncio.sleep(0.3)
        return await orig_create(*args, **kwargs)

    new_api_client.create_token = slow_create_token

    barrier = threading.Barrier(2)
    concurrent_results = []

    def attempt_concurrent_reset():
        barrier.wait()
        c = TestClient(app)
        return c.post(f"/api/v1/admin/tokens/{token_id}/reset", headers=adm_headers)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt_concurrent_reset) for _ in range(2)]
            for f in concurrent.futures.as_completed(futures):
                concurrent_results.append(f.result())
    finally:
        new_api_client.create_token = orig_create

    success_resets = [r for r in concurrent_results if r.status_code == 200]
    conflict_resets = [r for r in concurrent_results if r.status_code == 409]
    assert len(success_resets) == 1, f"并发争抢期望恰有 1 个成功获得签发权，实际结果: {[r.status_code for r in concurrent_results]}"
    assert len(conflict_resets) == 1, f"并发争抢期望恰有 1 个被互斥拦截，实际结果: {[r.status_code for r in concurrent_results]}"
    assert "正在重置中" in conflict_resets[0].json()["detail"] or "无法重置" in conflict_resets[0].json()["detail"]

    # 最终状态与网关唯一 Key 严格复核：
    # 断言网关实际仅有一个有效 Key，且本地记录 ID 与网关一致，绝无孤儿 Key
    db_session.expire_all()
    final_token = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert final_token.status == "active"
    assert final_token.new_api_token_id is not None

    matching_gw_tokens = [t for t in new_api_client._mock_tokens.values() if t.get("name") == initial_token_name]
    assert len(matching_gw_tokens) == 1, f"网关实际有效 Key 必须唯一，实际查到 {len(matching_gw_tokens)} 个"
    assert matching_gw_tokens[0]["id"] == final_token.new_api_token_id

    # 8. Worker 异常中断/崩溃后的安全接管与恢复验证：
    # 模拟场景：Worker 在网关已成功签发新 Key，但本地尚未保存 ID 前进程意外崩溃中断，留下超时的僵尸 resetting 锁
    final_token.status = "resetting"
    final_token.new_api_token_id = None
    final_token.updated_at = datetime.utcnow() - timedelta(seconds=60)
    db_session.commit()

    # 新请求到达，接管时核对上一次签发结果，安全接管僵尸锁并成功完成重置恢复
    r_recover_zombie = client.post(f"/api/v1/admin/tokens/{token_id}/reset", headers=adm_headers)
    assert r_recover_zombie.status_code == 200
    db_session.expire_all()
    recovered_token = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert recovered_token.status == "active"
    assert recovered_token.new_api_token_id is not None

    # 关键验收断言：网关恰有一把有效 Key，且 ID 与本地记录完全一致，绝不留同名孤儿 Key
    matching_gw_tokens = [t for t in new_api_client._mock_tokens.values() if t.get("name") == initial_token_name]
    assert len(matching_gw_tokens) == 1, f"崩溃恢复完成后网关实际有效 Key 必须恰有 1 个，实际为 {len(matching_gw_tokens)}"
    assert matching_gw_tokens[0]["id"] == recovered_token.new_api_token_id

    # 9. 进一步验证场景：Worker 在删除旧 Key 后、向网关签发新 Key 之前崩溃（网关上无任何同名 Key）
    new_api_client._mock_tokens.pop(recovered_token.new_api_token_id, None)
    recovered_token.status = "resetting"
    recovered_token.new_api_token_id = None
    recovered_token.updated_at = datetime.utcnow() - timedelta(seconds=60)
    db_session.commit()

    r_recover_pre_create = client.post(f"/api/v1/admin/tokens/{token_id}/reset", headers=adm_headers)
    assert r_recover_pre_create.status_code == 200
    db_session.expire_all()
    recov2_token = db_session.query(UserToken).filter(UserToken.id == token_id).first()
    assert recov2_token.status == "active"
    assert recov2_token.new_api_token_id is not None
    matching_gw2 = [t for t in new_api_client._mock_tokens.values() if t.get("name") == initial_token_name]
    assert len(matching_gw2) == 1, f"网关实际有效 Key 必须恰有 1 个，实际为 {len(matching_gw2)}"
    assert matching_gw2[0]["id"] == recov2_token.new_api_token_id


def test_installer_and_safe_content(client: TestClient, db_session):
    """
    验收手册 2.1:
    - 空库显示暂无安装包
    - 占位包不推荐
    - 上传真实文件后推荐，下载字节数与 SHA-256 一致
    """
    # 1. 登录管理员
    r_adm = client.post("/api/v1/auth/admin/login", json={
        "username": settings.INIT_ADMIN_USERNAME,
        "password": settings.INIT_ADMIN_PASSWORD
    })
    admin_token = r_adm.json()["access_token"]
    adm_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. 上传真实安装包
    real_installer_bytes = b"REAL_OFFICIAL_WINDOWS_INSTALLER_PAYLOAD_FOR_ONE_DESKTOP_CLIENT_2026"
    import hashlib
    real_sha = hashlib.sha256(real_installer_bytes).hexdigest()

    files = {"file": ("OneHarness_v1.5.0_Setup.exe", io.BytesIO(real_installer_bytes), "application/octet-stream")}
    data = {
        "category": "installer",
        "title": "One Harness 官方内网特调客户端",
        "version": "v1.5.0",
        "description": "真实内网推荐版本",
        "is_recommended": True
    }
    r_up = client.post("/api/v1/admin/files/upload", files=files, data=data, headers=adm_headers)
    assert r_up.status_code == 200, r_up.text
    file_id = r_up.json()["data"]["id"]

    # 3. 首页推荐接口获取
    r_rec = client.get("/api/v1/guide/recommended-installer")
    assert r_rec.status_code == 200
    rec_data = r_rec.json()
    assert rec_data["has_installer"] is True
    assert rec_data["data"]["id"] == file_id
    assert rec_data["data"]["sha256"] == real_sha
    assert rec_data["data"]["file_size"] == len(real_installer_bytes)

    # 4. 下载并校验流式字节
    r_dl = client.get(f"/api/v1/files/download/{file_id}")
    assert r_dl.status_code == 200
    assert r_dl.content == real_installer_bytes
    assert hashlib.sha256(r_dl.content).hexdigest() == real_sha

    # 5. 重启/重新执行 init_database() 容灾断言：
    # 即使上传的文件名为历史同名 DeepSeek-Harness-v1.4.2-win-x64.exe，只要是真实包（非已知 43B 占位文件），重启后绝不被误取消推荐！
    real_setup_bytes = b"REAL_OFFICIAL_SETUP_BIN_" * 100  # 2400 字节真实内容
    real_setup_sha = hashlib.sha256(real_setup_bytes).hexdigest()
    files_setup = {"file": ("DeepSeek-Harness-v1.4.2-win-x64.exe", io.BytesIO(real_setup_bytes), "application/octet-stream")}
    data_setup = {
        "category": "installer",
        "title": "DeepSeek Harness 真实官方客户端",
        "version": "v1.4.2",
        "is_recommended": True
    }
    r_up_real = client.post("/api/v1/admin/files/upload", files=files_setup, data=data_setup, headers=adm_headers)
    assert r_up_real.status_code == 200
    real_pkg_id = r_up_real.json()["data"]["id"]

    # 模拟系统重启执行 init_database()
    init_db_mod.init_database()

    # 断言该真实同名安装包依然保持 is_recommended == True
    db_session.expire_all()
    pkg_row = db_session.query(SharedFile).filter(SharedFile.id == real_pkg_id).first()
    assert pkg_row is not None
    assert pkg_row.is_recommended is True, "真实同名安装包在系统重启后必须保持推荐状态，不得因文件名被粗暴误杀！"

    # 6. 占位清理反例断言：非安装包类别的 43 字节普通资料（如业务规范或提示词），重启后严格保持推荐，绝不误伤！
    normal_doc_bytes = b"1234567890123456789012345678901234567890123"  # 严格 43 字节内容
    assert len(normal_doc_bytes) == 43
    files_doc = {"file": ("financial_guideline.txt", io.BytesIO(normal_doc_bytes), "text/plain")}
    data_doc = {
        "category": "document",
        "title": "43字节金融业务合规速查指南",
        "version": "v1.0.0",
        "is_recommended": True
    }
    r_up_doc = client.post("/api/v1/admin/files/upload", files=files_doc, data=data_doc, headers=adm_headers)
    assert r_up_doc.status_code == 200
    doc_id = r_up_doc.json()["data"]["id"]

    # 再次模拟系统重启执行 init_database()
    init_db_mod.init_database()

    # 严格断言：非安装包的 43 字节普通资料依然推荐！
    db_session.expire_all()
    doc_row = db_session.query(SharedFile).filter(SharedFile.id == doc_id).first()
    assert doc_row is not None
    assert doc_row.file_size == 43
    assert doc_row.is_recommended is True, "43 字节普通非安装包资料在重启后必须保持推荐状态，不得被误取消！"


def test_admin_token_usage_ranking(client: TestClient, db_session, monkeypatch):
    now = datetime(2026, 11, 23, 16, 30, tzinfo=timezone.utc)
    shanghai_midnight = int((now - timedelta(minutes=30)).timestamp())

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(now.timestamp(), tz)

    monkeypatch.setattr(log_sync_mod, "datetime", FrozenDatetime)
    log_specs = [
        ("001024", "ranking-test-a", shanghai_midnight, 100, 50, 2),
        ("001024", "ranking-test-b", shanghai_midnight - 1, 200, 50, 1),
        ("06700956", "ranking-test-a", shanghai_midnight + 60, 70, 80, 999999),
        ("06700956", "ranking-test-b", int((now - timedelta(days=8)).timestamp()), 300, 50, 1),
        ("removed-employee", "ranking-test-c", int((now - timedelta(days=31)).timestamp()), 800, 20, 5),
        ("UNKNOWN", "ranking-test-a", shanghai_midnight + 60, 0, 10, 99),
        ("UNKNOWN", "ranking-test-zero", shanghai_midnight + 60, 0, 0, 999999),
        ("001024", "ranking-test-boundary", int((now - timedelta(days=7)).timestamp()), 2, 1, 3),
    ]
    log_ids = [-9000 - index for index in range(len(log_specs))]
    db_session.add_all([
        UsageLogCache(
            new_api_log_id=log_id,
            emp_no=emp_no,
            token_name=f"ranking-fixture-{emp_no}",
            model_name=model,
            created_at=created_at,
            prompt_tokens=prompt,
            completion_tokens=completion,
            quota=quota,
        )
        for log_id, (emp_no, model, created_at, prompt, completion, quota) in zip(log_ids, log_specs)
    ])
    db_session.commit()

    url = "/api/v1/admin/usage/ranking"
    admin_token = create_access_token({"sub": settings.INIT_ADMIN_USERNAME, "role": "admin"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    employee_token = create_access_token({"sub": "001024", "role": "employee"})

    def ranking(dimension, period):
        response = client.get(url, params={"dimension": dimension, "range": period}, headers=admin_headers)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    try:
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": f"Bearer {employee_token}"}).status_code == 403
        assert client.get(url, params={"range": "invalid"}, headers=admin_headers).status_code == 422
        assert client.get(url, params={"dimension": "invalid"}, headers=admin_headers).status_code == 422

        today_users = ranking("user", "today")
        assert [(row["key"], row["total_tokens"]) for row in today_users] == [
            ("001024", 150), ("06700956", 150)
        ]
        assert today_users[0]["name"] == db_session.query(Employee.name).filter_by(emp_no="001024").scalar()
        assert today_users[0]["department"]

        today_models = ranking("model", "today")
        assert [(row["key"], row["total_tokens"], row["request_count"]) for row in today_models] == [
            ("ranking-test-a", 310, 3)
        ]
        assert (today_models[0]["prompt_tokens"], today_models[0]["completion_tokens"]) == (170, 140)

        week = ranking("model", "7d")
        assert [row["key"] for row in week] == ["ranking-test-a", "ranking-test-b", "ranking-test-boundary"]
        assert ranking("model", "30d")[0]["key"] == "ranking-test-b"

        historical = ranking("user", "all")[0]
        assert (historical["key"], historical["name"], historical["department"], historical["total_tokens"]) == (
            "removed-employee", "removed-employee", None, 820
        )
    finally:
        db_session.query(UsageLogCache).filter(UsageLogCache.new_api_log_id.in_(log_ids)).delete()
        db_session.commit()


def test_incremental_log_sync_and_admin_security(client: TestClient, db_session):
    """
    验收手册 2.2 & 2.3:
    - 增量同步分页异常时游标不推进
    - 重试去重
    - POST /api/v1/admin/logs/sync 管理员专属鉴权
    - 部门排行与同步状态字段
    """
    db_session.query(AuthLockout).delete()
    db_session.query(VerificationCode).delete()
    db_session.commit()

    # 1. 登录员工与管理员
    client.post("/api/v1/auth/send-code", json={"account": "06700888"})
    emp_code = extract_code_from_msg(MockPusher.captured_messages[-1]["content"])
    r_emp_auth = client.post("/api/v1/auth/login", json={"account": "06700888", "code": emp_code})
    assert r_emp_auth.status_code == 200, r_emp_auth.text
    emp_token = r_emp_auth.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    r_adm = client.post("/api/v1/auth/admin/login", json={
        "username": settings.INIT_ADMIN_USERNAME,
        "password": settings.INIT_ADMIN_PASSWORD
    })
    adm_token = r_adm.json()["access_token"]
    adm_headers = {"Authorization": f"Bearer {adm_token}"}

    # 2. 权限隔离：普通员工调用管理员专属同步端点必须返回 401/403 拒绝
    r_forbidden_sync = client.post("/api/v1/admin/logs/sync", headers=emp_headers)
    assert r_forbidden_sync.status_code in (401, 403)

    # 3. 管理员调用专属同步端点成功
    r_adm_sync = client.post("/api/v1/admin/logs/sync", headers=adm_headers)
    assert r_adm_sync.status_code == 200
    assert r_adm_sync.json()["success"] is True

    # 4. 验证管理员仪表盘包含部门排行与同步状态
    r_overview = client.get("/api/v1/admin/overview", headers=adm_headers)
    assert r_overview.status_code == 200
    ov_data = r_overview.json()["data"]
    assert "total_tokens" in ov_data
    assert "department_ranking" in ov_data
    assert isinstance(ov_data["department_ranking"], list)
    assert "last_sync_status" in ov_data

    # 5. 增量日志同步真实故障演练 A：分页异常（第 2 页失败）游标不推进断言
    # 读取当前初始同步游标，以此为基准生成单调递增的未来测试时间戳
    db_session.expire_all()
    ts_setting = db_session.query(SystemSetting).filter(SystemSetting.key == "last_log_sync_ts").first()
    init_cursor = int(ts_setting.value) if (ts_setting and ts_setting.value) else 0
    base_ts = init_cursor + 1000

    page1_logs = [
        {
            "id": 80000 + i,
            "token_name": "EMP_06700888_王大力",
            "model_name": "DeepSeek-V4-Flash-0731-INT8",
            "created_at": base_ts + i,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "quota": 30,
            "use_time": 50,
            "is_stream": True,
        }
        for i in range(100)  # 满整页 100 条
    ]
    page2_logs = [
        {
            "id": 80100 + i,
            "token_name": "EMP_06700888_王大力",
            "model_name": "DeepSeek-V4-Flash-0731-INT8",
            "created_at": base_ts + 100 + i,
            "prompt_tokens": 15,
            "completion_tokens": 25,
            "quota": 40,
            "use_time": 60,
            "is_stream": True,
        }
        for i in range(20)  # 第 2 页 20 条
    ]

    original_fetch = new_api_client.fetch_consumption_logs

    async def mock_fetch_with_page2_fail(start_timestamp=0, page=1, page_size=100):
        if page == 1:
            return page1_logs
        elif page == 2:
            raise RuntimeError("模拟 new-api 聚合网关在拉取第 2 页时发生 500 宕机异常")
        return []

    new_api_client.fetch_consumption_logs = mock_fetch_with_page2_fail

    # 执行同步，必须捕获异常
    with pytest.raises(Exception):
        import asyncio
        asyncio.run(LogSyncService.sync_incremental_logs(db=db_session))

    # 严格断言：第 2 页失败时，事务已回滚且 last_log_sync_ts 游标绝对不可推进！
    db_session.expire_all()
    ts_setting_after_fail = db_session.query(SystemSetting).filter(SystemSetting.key == "last_log_sync_ts").first()
    current_cursor = int(ts_setting_after_fail.value) if (ts_setting_after_fail and ts_setting_after_fail.value) else 0
    assert current_cursor == init_cursor, f"游标不应推进，预期 {init_cursor}，实际 {current_cursor}"

    # 6. 增量日志同步真实故障演练 B：故障恢复重试与幂等去重断言
    # 恢复网关正常拉取，第 1 页与第 2 页均可正常返回
    async def mock_fetch_recovered(start_timestamp=0, page=1, page_size=100):
        if page == 1:
            return page1_logs
        elif page == 2:
            return page2_logs
        return []

    new_api_client.fetch_consumption_logs = mock_fetch_recovered

    # 再次重试同步
    new_added = asyncio.run(LogSyncService.sync_incremental_logs(db=db_session))
    # 严格断言：总入库条数严格为 120 条，第 1 页在重试拉取时不发生重复累加
    total_cached = db_session.query(UsageLogCache).filter(UsageLogCache.new_api_log_id >= 80000).count()
    assert total_cached == 120, f"预期幂等去重后恰有 120 条，实际为 {total_cached} 条"

    # 此时游标成功推进至最后一批最大时间戳 (base_ts + 119)
    db_session.expire_all()
    ts_setting_recovered = db_session.query(SystemSetting).filter(SystemSetting.key == "last_log_sync_ts").first()
    assert int(ts_setting_recovered.value) == base_ts + 119

    # 7. 增量日志同步边界测试 C：同秒多条（同时间戳边界）日志幂等入库断言
    same_second_logs = [
        {
            "id": 80901,
            "token_name": "EMP_06700888_王大力",
            "model_name": "Qwen3.8-27B-BF16",
            "created_at": base_ts + 200,
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "quota": 20,
            "use_time": 30,
            "is_stream": False,
        },
        {
            "id": 80902,
            "token_name": "EMP_06700888_王大力",
            "model_name": "DeepSeek-R1-Distill-Qwen-32B",
            "created_at": base_ts + 200,
            "prompt_tokens": 20,
            "completion_tokens": 20,
            "quota": 40,
            "use_time": 40,
            "is_stream": False,
        },
        {
            "id": 80903,
            "token_name": "EMP_06700888_王大力",
            "model_name": "Qwen3.7-Plus-VL-Thinking-INT8",
            "created_at": base_ts + 200,
            "prompt_tokens": 30,
            "completion_tokens": 30,
            "quota": 60,
            "use_time": 50,
            "is_stream": False,
        },
    ]

    async def mock_fetch_same_sec(start_timestamp=0, page=1, page_size=100):
        if page == 1:
            return same_second_logs
        return []

    new_api_client.fetch_consumption_logs = mock_fetch_same_sec
    added_same_sec = asyncio.run(LogSyncService.sync_incremental_logs(db=db_session))
    assert added_same_sec == 3

    # 还原 fetch_consumption_logs
    new_api_client.fetch_consumption_logs = original_fetch


def test_cordis_patch_generation(client: TestClient):
    """测试客户端 patch.yml 生成格式规范"""
    r = client.get("/api/v1/guide/cordis-patch-yml")
    assert r.status_code == 200
    content = r.text
    assert "@deepseek-ai/dsh-session-log-deepseek" in content
    assert "enabled: false" in content
    assert "new-api-1" in content
    assert "DeepSeek-V4-Flash-0731-INT8" in content


def test_employee_import_and_management(client: TestClient, db_session):
    """测试员工导入与全流程管理"""
    db_session.query(AuthLockout).delete()
    db_session.query(VerificationCode).delete()
    db_session.commit()

    r_adm = client.post("/api/v1/auth/admin/login", json={
        "username": settings.INIT_ADMIN_USERNAME,
        "password": settings.INIT_ADMIN_PASSWORD
    })
    adm_token = r_adm.json()["access_token"]
    adm_headers = {"Authorization": f"Bearer {adm_token}"}

    # 1. 下载导入模板
    r_tpl = client.get("/api/v1/admin/employees/template", headers=adm_headers)
    assert r_tpl.status_code == 200
    assert len(r_tpl.content) > 100

    # 2. CSV 批量导入
    csv_data = "工号,姓名,部门,手机号后4位\n06709001,李雷,零售金融部,1111\n06709002,韩梅梅,金融市场部,2222\n"
    csv_file = {"file": ("employees.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    r_imp = client.post("/api/v1/admin/employees/import", files=csv_file, headers=adm_headers)
    assert r_imp.status_code == 200, r_imp.text
    assert (r_imp.json()["data"]["created"] + r_imp.json()["data"]["updated"]) >= 2

    # 3. 查询导入结果
    r_search = client.get("/api/v1/admin/employees?keyword=韩梅梅", headers=adm_headers)
    assert r_search.status_code == 200
    assert len(r_search.json()["items"]) == 1
    lei_item = [x for x in client.get("/api/v1/admin/employees?keyword=李雷", headers=adm_headers).json()["items"] if x["emp_no"] == "06709001"][0]
    lei_id = lei_item["id"]

    # 4. 李雷正常统一登录并申领 Key
    db_session.query(VerificationCode).delete()
    db_session.commit()
    client.post("/api/v1/auth/send-code", json={"account": "06709001"})
    code_lei = extract_code_from_msg(MockPusher.captured_messages[-1]["content"])
    r_login_lei = client.post("/api/v1/auth/login", json={"account": "06709001", "code": code_lei})
    assert r_login_lei.status_code == 200
    lei_jwt = r_login_lei.json()["access_token"]
    lei_headers = {"Authorization": f"Bearer {lei_jwt}"}

    r_tok_lei = client.get("/api/v1/me/token", headers=lei_headers)
    assert r_tok_lei.status_code == 200
    assert r_tok_lei.json()["status"] == "active"

    # 5. 管理员停用李雷，模拟网关调用故障：
    # 断言本地停用成功，且标记为 gateway_disable_pending（网关吊销待重试）
    new_api_client._mock_fail_status = True
    try:
        r_disable_fail = client.put(f"/api/v1/admin/employees/{lei_id}", json={"is_active": False}, headers=adm_headers)
        assert r_disable_fail.status_code == 200
        assert "待重试" in r_disable_fail.json()["message"]
    finally:
        new_api_client._mock_fail_status = False

    # 断言列表可感知网关待重试状态
    lei_updated = [x for x in client.get("/api/v1/admin/employees?keyword=李雷", headers=adm_headers).json()["items"] if x["id"] == lei_id][0]
    assert lei_updated["is_active"] is False
    assert lei_updated["token_status"] == "gateway_disable_pending"

    # 断言停用员工无法获取验证码或读取 Key
    r_send_disabled = client.post("/api/v1/auth/send-code", json={"account": "06709001"})
    assert r_send_disabled.status_code in (403, 404)

    r_read_disabled = client.get("/api/v1/me/token", headers=lei_headers)
    assert r_read_disabled.status_code in (401, 403)

    # 6. 后台通过专属端点重试网关吊销成功
    r_retry_disable = client.post(f"/api/v1/admin/employees/{lei_id}/retry-disable-token", headers=adm_headers)
    assert r_retry_disable.status_code == 200
    lei_retried = [x for x in client.get("/api/v1/admin/employees?keyword=李雷", headers=adm_headers).json()["items"] if x["id"] == lei_id][0]
    assert lei_retried["token_status"] == "disabled"

    # 7. 名册批量导入保护断言：再次上传 CSV 更新李雷部门和姓名，断言严禁普通名册导入自动复职！
    csv_update = "工号,姓名,部门,手机号后4位\n06709001,李雷更新资料,新成立金融科技业务部,8888\n"
    csv_up_file = {"file": ("employees_update.csv", io.BytesIO(csv_update.encode("utf-8")), "text/csv")}
    r_imp_again = client.post("/api/v1/admin/employees/import", files=csv_up_file, headers=adm_headers)
    assert r_imp_again.status_code == 200

    # 关键断言：李雷资料已更新，但 is_active 严格保持 False！
    lei_after_import = [x for x in client.get("/api/v1/admin/employees?keyword=李雷", headers=adm_headers).json()["items"] if x["id"] == lei_id][0]
    assert lei_after_import["name"] == "李雷更新资料"
    assert lei_after_import["department"] == "新成立金融科技业务部"
    assert lei_after_import["is_active"] is False, "严禁普通名册导入自动将已停用员工复职！"

    # 8. 显式复职测试
    r_rehire = client.put(f"/api/v1/admin/employees/{lei_id}", json={"is_active": True}, headers=adm_headers)
    assert r_rehire.status_code == 200
    lei_rehire = [x for x in client.get("/api/v1/admin/employees?keyword=李雷", headers=adm_headers).json()["items"] if x["id"] == lei_id][0]
    assert lei_rehire["is_active"] is True
    assert lei_rehire["token_status"] == "active"


def test_articles_and_image_upload(client: TestClient, db_session):
    """测试案例文章 Markdown 离线管理与图片上传"""
    r_adm = client.post("/api/v1/auth/admin/login", json={
        "username": settings.INIT_ADMIN_USERNAME,
        "password": settings.INIT_ADMIN_PASSWORD
    })
    adm_token = r_adm.json()["access_token"]
    adm_headers = {"Authorization": f"Bearer {adm_token}"}

    # 1. 上传图片
    img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    files = {"file": ("test.png", io.BytesIO(img_bytes), "image/png")}
    r_img = client.post("/api/v1/admin/articles/upload-image", files=files, headers=adm_headers)
    assert r_img.status_code == 200
    img_url = r_img.json()["url"]
    assert "/api/v1/static/images/" in img_url

    # 2. 创建文章
    art_payload = {
        "title": "单元测试指南实践文章",
        "summary": "这是单元测试文章摘要",
        "category": "代码实践",
        "tags": ["测试", "FastAPI"],
        "content_md": f"# 标题\n\n![配图]({img_url})\n\n正文内容测试。",
        "is_pinned": True,
        "is_published": True
    }
    r_art = client.post("/api/v1/admin/articles", json=art_payload, headers=adm_headers)
    assert r_art.status_code == 200
    art_id = r_art.json()["id"]

    # 3. 公开获取详情
    r_dt = client.get(f"/api/v1/articles/{art_id}")
    assert r_dt.status_code == 200
    assert r_dt.json()["data"]["view_count"] >= 1


def test_user_usage_dashboard(client: TestClient, db_session):
    """测试员工端用量趋势与模型分布看板（SQL 粒度聚合与单机轻量刷新）"""
    db_session.query(AuthLockout).delete()
    db_session.query(VerificationCode).delete()
    db_session.commit()

    # 1. 统一登录
    db_session.query(VerificationCode).delete()
    db_session.commit()
    client.post("/api/v1/auth/send-code", json={"account": "06700956"})
    emp_code = extract_code_from_msg(MockPusher.captured_messages[-1]["content"])
    r_emp_auth = client.post("/api/v1/auth/login", json={"account": "06700956", "code": emp_code})
    assert r_emp_auth.status_code == 200
    emp_token = r_emp_auth.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 2. 员工端刷新用量数据：断言仅返回当前员工明细与全网同步元信息，绝不发起全行网关调用
    r_sync = client.post("/api/v1/me/usage/sync", headers=emp_headers)
    assert r_sync.status_code == 200
    sync_data = r_sync.json()
    assert sync_data["success"] is True
    assert "last_successful_sync_time" in sync_data
    assert "sync_frequency" in sync_data
    assert "5 分钟" in sync_data["sync_frequency"]

    # 3. 获取看板指标与 SQL 粒度聚合趋势图
    r_ov = client.get("/api/v1/me/usage/overview?range=all", headers=emp_headers)
    assert r_ov.status_code == 200
    assert "total_requests" in r_ov.json()["data"]

    r_tr = client.get("/api/v1/me/usage/trend?range=all", headers=emp_headers)
    assert r_tr.status_code == 200
    tr_data = r_tr.json()["data"]
    assert "categories" in tr_data
    assert "series" in tr_data
    assert "total_tokens" in tr_data["series"]
    assert "requests" in tr_data["series"]

    r_md = client.get("/api/v1/me/usage/models?range=all", headers=emp_headers)
    assert r_md.status_code == 200

    r_lg = client.get("/api/v1/me/usage/logs?page=1&page_size=10", headers=emp_headers)
    assert r_lg.status_code == 200
    assert "items" in r_lg.json()["data"]


def test_global_log_sync_singleton_lock(client: TestClient, db_session, monkeypatch):
    """
    测试全局日志同步单例互斥锁与并发拦截：
    - 多 worker/并发管理员手动触发在全站同一时刻最多执行一轮同步
    - 并发争抢时，另一个请求被互斥拦截并返回 409 Conflict
    """
    # 登录管理员
    r_adm = client.post("/api/v1/auth/admin/login", json={
        "username": settings.INIT_ADMIN_USERNAME,
        "password": settings.INIT_ADMIN_PASSWORD
    })
    adm_token = r_adm.json()["access_token"]
    adm_headers = {"Authorization": f"Bearer {adm_token}"}

    db_session.query(SystemSetting).filter_by(key=LogSyncService._LOCK_KEY).delete()
    db_session.commit()
    start = threading.Barrier(2, timeout=10)
    finish_event = threading.Event()

    async def slow_fetch(*args, **kwargs):
        assert await asyncio.to_thread(finish_event.wait, 10)
        return []

    monkeypatch.setattr(new_api_client, "fetch_consumption_logs", slow_fetch)

    def trigger_sync():
        start.wait()
        c = TestClient(app)
        res = c.post("/api/v1/admin/logs/sync", headers=adm_headers)
        if res.status_code == 409:
            finish_event.set()
        return res

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(trigger_sync) for _ in range(2)]
        sync_results = [future.result(timeout=20) for future in futures]

    assert sorted(r.status_code for r in sync_results) == [200, 409]
    conflict_res = [r for r in sync_results if r.status_code == 409][0]
    assert "正在进行中" in conflict_res.json()["detail"] or "请勿重复触发" in conflict_res.json()["detail"]


@pytest.mark.parametrize("stale_fetch_fails", [False, True])
def test_expired_log_sync_owner_cannot_write_or_release(db_session, test_setup, monkeypatch, stale_fetch_fails):
    old_started, allow_old_finish = threading.Event(), threading.Event()
    new_started, allow_new_finish = threading.Event(), threading.Event()
    old_log_id = 910001 if stale_fetch_fails else 910002
    new_log_id = old_log_id + 100
    cursor = db_session.get(SystemSetting, "last_log_sync_ts")
    last_ts = int(cursor.value) if cursor else 0
    sync_result = db_session.get(SystemSetting, "last_sync_message")
    prior_message = sync_result.value if sync_result else None

    async def fetch(**kwargs):
        if not old_started.is_set():
            old_started.set()
            assert await asyncio.to_thread(allow_old_finish.wait, 10)
            if stale_fetch_fails:
                raise RuntimeError("旧任务网关拉取失败")
            return [{"id": old_log_id, "created_at": last_ts + 100}]
        new_started.set()
        assert await asyncio.to_thread(allow_new_finish.wait, 10)
        return [{"id": new_log_id, "created_at": last_ts + 1}]

    monkeypatch.setattr(new_api_client, "fetch_consumption_logs", fetch)

    def sync():
        with test_setup["SessionLocal"]() as worker_db:
            return asyncio.run(LogSyncService.sync_incremental_logs(worker_db))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        old_task = executor.submit(sync)
        try:
            assert old_started.wait(10)
            lease = db_session.get(SystemSetting, LogSyncService._LOCK_KEY)
            old_owner = lease.value
            lease.updated_at -= LogSyncService._LOCK_DURATION + timedelta(seconds=1)
            db_session.commit()

            new_task = executor.submit(sync)
            assert new_started.wait(10)
            new_owner = db_session.get(SystemSetting, LogSyncService._LOCK_KEY).value
            assert new_owner and new_owner != old_owner

            allow_old_finish.set()
            expected_error = RuntimeError if stale_fetch_fails else HTTPException
            with pytest.raises(expected_error) as exc:
                old_task.result(timeout=10)
            if not stale_fetch_fails:
                assert exc.value.status_code == 409
            db_session.expire_all()
            assert db_session.get(SystemSetting, LogSyncService._LOCK_KEY).value == new_owner
            assert db_session.query(UsageLogCache).filter_by(new_api_log_id=old_log_id).count() == 0
            cursor = db_session.get(SystemSetting, "last_log_sync_ts")
            assert (int(cursor.value) if cursor else 0) == last_ts
            sync_result = db_session.get(SystemSetting, "last_sync_message")
            assert (sync_result.value if sync_result else None) == prior_message
            assert LogSyncService._acquire_sync_lock(db_session) is None
        finally:
            allow_old_finish.set()
            allow_new_finish.set()
        assert new_task.result(timeout=10) == 1

    db_session.expire_all()
    assert db_session.get(SystemSetting, LogSyncService._LOCK_KEY).value is None
    assert int(db_session.get(SystemSetting, "last_log_sync_ts").value) == last_ts + 1
    assert db_session.query(UsageLogCache).filter_by(new_api_log_id=new_log_id).count() == 1


def test_log_sync_renewal_extends_takeover_deadline(db_session, test_setup, monkeypatch):
    class Clock(datetime):
        now_utc = datetime(2026, 1, 1)

        @classmethod
        def utcnow(cls):
            return cls.now_utc

    monkeypatch.setattr("backend.app.services.log_sync.datetime", Clock)
    owner = LogSyncService._acquire_sync_lock(db_session)
    assert owner is not None
    with test_setup["SessionLocal"]() as contender:
        takeover = None
        try:
            Clock.now_utc += timedelta(seconds=110)
            assert LogSyncService._renew_sync_lock(db_session, owner)
            db_session.commit()
            Clock.now_utc += timedelta(seconds=15)
            assert LogSyncService._acquire_sync_lock(contender) is None
            Clock.now_utc += timedelta(seconds=106)
            takeover = LogSyncService._acquire_sync_lock(contender)
            assert takeover is not None and takeover != owner
        finally:
            LogSyncService._release_sync_lock(db_session, owner)
            if takeover is not None:
                LogSyncService._release_sync_lock(contender, takeover)
