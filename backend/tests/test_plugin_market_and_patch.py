from __future__ import annotations
import io
import json
import sys
import tarfile
from pathlib import Path
import httpx
import yaml
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.employee import Employee
from backend.app.models.setting import SystemSetting
from backend.app.services.plugin_validator import PluginValidationError, validate_plugin_tgz


def _build_tgz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_tgz_validator_blocks_path_traversal_and_lifecycle_scripts():
    """校验 .tgz 严格阻断路径穿越、非法包名与高危生命周期脚本"""
    traversal_tgz = _build_tgz({
        "package/package.json": json.dumps({"name": "@rgone/dsh-ok", "version": "1.0.0"}).encode(),
        "package/../../evil.sh": b"echo pwned",
    })
    try:
        validate_plugin_tgz(traversal_tgz)
        assert False, "应拦截路径穿越"
    except PluginValidationError as exc:
        assert "路径穿越" in str(exc) or "非法" in str(exc)

    lifecycle_tgz = _build_tgz({
        "package/package.json": json.dumps({
            "name": "@rgone/dsh-risky",
            "version": "1.0.0",
            "scripts": {"postinstall": "curl http://bad"},
        }).encode(),
    })
    try:
        validate_plugin_tgz(lifecycle_tgz, allow_lifecycle_scripts=False)
        assert False, "应默认拒绝生命周期脚本"
    except PluginValidationError as exc:
        assert "postinstall" in str(exc)

    valid_tgz = _build_tgz({
        "package/package.json": json.dumps({
            "name": "@rgone/dsh-clean",
            "version": "1.2.3",
            "description": "Clean test plugin",
        }).encode(),
        "package/index.js": b"module.exports = {};",
    })
    validated = validate_plugin_tgz(valid_tgz)
    assert validated.name == "@rgone/dsh-clean"
    assert validated.version == "1.2.3"
    assert validated.has_lifecycle_scripts is False


def test_plugin_submission_review_verdaccio_publish_and_format1_index(
    client: TestClient, db_session, monkeypatch
):
    """完整闭环：员工投稿 .tgz -> 小秘书通知审核员 -> 管理员审核自动 PUT Verdaccio -> /market/index.json"""
    emp = db_session.query(Employee).filter(Employee.emp_no == "06700956").first()
    assert emp is not None
    emp_token = create_access_token({
        "sub": emp.emp_no,
        "name": emp.name,
        "department": emp.department,
        "role": "employee",
    })
    adm_token = create_access_token({"sub": settings.INIT_ADMIN_USERNAME, "role": "admin"})

    monkeypatch.setattr(settings, "RGONE_PUBLIC_URL", "https://one.internal")
    monkeypatch.setattr(settings, "VERDACCIO_URL", "http://mock-verdaccio:4873")
    monkeypatch.setattr(settings, "VERDACCIO_AUTH_TOKEN", "verdaccio-token-xyz")
    monkeypatch.setattr(settings, "PLUGIN_REVIEWER_EMP_NOS", "06701099")

    # 配置测试小秘书地址
    db_session.query(SystemSetting).filter(SystemSetting.key == "xiaomishu_api").delete()
    db_session.add(SystemSetting(key="xiaomishu_api", value="http://mock-xms.internal/send"))
    db_session.commit()

    xms_messages = []
    verdaccio_puts = []

    orig_post = httpx.AsyncClient.post
    orig_put = httpx.AsyncClient.put

    async def mock_post(self, url, *args, **kwargs):
        if "mock-xms.internal" in str(url):
            xms_messages.append(kwargs.get("json") or {})
            return httpx.Response(status_code=200, json={"errcode": 0})
        return await orig_post(self, url, *args, **kwargs)

    async def mock_put(self, url, *args, **kwargs):
        if "mock-verdaccio" in str(url):
            verdaccio_puts.append({
                "url": str(url),
                "headers": dict(kwargs.get("headers") or {}),
                "json": kwargs.get("json") or {},
            })
            return httpx.Response(status_code=201, json={"ok": "created"})
        return await orig_put(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    monkeypatch.setattr(httpx.AsyncClient, "put", mock_put)

    # 1. 上架前 /market/index.json 为空列表但格式符合 Format-1
    r_idx0 = client.get("/market/index.json")
    assert r_idx0.status_code == 200
    idx0 = r_idx0.json()
    assert idx0["version"] == 1
    assert idx0["registry"] == "https://one.internal/npm"
    assert isinstance(idx0["plugins"], list)

    # 2. 员工投稿 .tgz
    tgz_bytes = _build_tgz({
        "package/package.json": json.dumps({
            "name": "@rgone/dsh-bond-helper",
            "version": "1.0.0",
            "description": "债券助手快捷扩展",
        }).encode(),
        "package/index.js": b"export default {};",
    })
    r_sub = client.post(
        "/api/v1/market/submissions",
        data={
            "submit_source": "tgz",
            "display_name": "债券报价助手",
            "category": "业务助手",
            "tags": "债券,快捷指令",
            "changelog": "初始版本",
        },
        files={"file": ("dsh-bond-helper-1.0.0.tgz", tgz_bytes, "application/gzip")},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert r_sub.status_code == 200
    plugin_data = r_sub.json()["plugin"]
    assert plugin_data["status"] == "pending"
    version_id = plugin_data["versions"][0]["id"]
    assert any(m.get("touser") == "06701099" for m in xms_messages)

    # 3. 管理员审核通过并自动推送 Verdaccio
    r_approve = client.post(
        f"/api/v1/admin/plugins/versions/{version_id}/approve",
        json={"comment": "安全核验通过"},
        headers={"Authorization": f"Bearer {adm_token}"},
    )
    assert r_approve.status_code == 200
    assert r_approve.json()["publish_status"] == "published"
    assert len(verdaccio_puts) == 1
    assert verdaccio_puts[0]["url"] == "http://mock-verdaccio:4873/%40rgone%2Fdsh-bond-helper"
    assert verdaccio_puts[0]["headers"]["Authorization"] == "Bearer verdaccio-token-xyz"
    assert "dsh-bond-helper-1.0.0.tgz" in verdaccio_puts[0]["json"]["_attachments"]
    assert any(m.get("touser") == "06700956" for m in xms_messages)

    # 4. 验证 /market/index.json 与门户接口返回已上架插件
    r_idx1 = client.get("/market/index.json")
    assert r_idx1.status_code == 200
    idx1 = r_idx1.json()
    assert idx1["version"] == 1
    assert "业务助手" in idx1["categories"]
    matched = [p for p in idx1["plugins"] if p["name"] == "@rgone/dsh-bond-helper"]
    assert len(matched) == 1
    assert matched[0]["version"] == "1.0.0"
    assert matched[0]["displayName"] == "债券报价助手"


def test_cordis_patch_four_in_one_logged_in_and_degraded(client: TestClient, db_session, monkeypatch):
    """验证四合一 cordis.patch.yml：登录员工注入专属 ide-token，Hub 不可达或未登录优雅降级"""
    monkeypatch.setattr(settings, "RGONE_PUBLIC_URL", "https://rgone.internal")
    monkeypatch.setattr(settings, "CAPABILITY_HUB_BASE_URL", "http://mock-hub:8080")
    monkeypatch.setattr(settings, "CAPABILITY_HUB_INTERNAL_SECRET", "internal-sec")

    emp = db_session.query(Employee).filter(Employee.emp_no == "06700956").first()
    emp_token = create_access_token({
        "sub": emp.emp_no,
        "name": emp.name,
        "department": emp.department,
        "role": "employee",
    })

    # 1. 未登录下载：四合一结构完整且使用占位符
    r_anon = client.get("/api/v1/guide/cordis-patch-yml")
    assert r_anon.status_code == 200
    anon_items = yaml.safe_load(r_anon.text)
    assert isinstance(anon_items, list)
    ids_anon = {item["id"]: item for item in anon_items}
    assert ids_anon["plugin-market"]["config"] == {
        "registry": "https://rgone.internal/npm",
        "marketUrl": "https://rgone.internal/market/index.json",
    }
    assert ids_anon["mcp-client"]["config"]["servers"]["rgone-hub"]["headers"]["Authorization"] == "Bearer <YOUR_MCP_TOKEN>"

    # 2. 已登录下载且 Hub 正常签发 ide-token
    hub_mode = {"ok": True}
    orig_post = httpx.AsyncClient.post

    async def mock_hub_post(self, url, *args, **kwargs):
        if "mock-hub" in str(url):
            if hub_mode["ok"]:
                return httpx.Response(
                    status_code=200,
                    json={
                        "user_id": "06700956",
                        "token": "ide-jwt-token-888",
                        "gateway_url": "https://rgone.internal/mcp",
                    },
                )
            return httpx.Response(status_code=503, json={"detail": "down"})
        return await orig_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_hub_post)

    r_auth = client.get(
        "/api/v1/guide/cordis-patch-yml",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert r_auth.status_code == 200
    auth_items = yaml.safe_load(r_auth.text)
    ids_auth = {item["id"]: item for item in auth_items}
    assert ids_auth["mcp-client"]["config"]["servers"]["rgone-hub"]["url"] == "https://rgone.internal/mcp"
    assert ids_auth["mcp-client"]["config"]["servers"]["rgone-hub"]["headers"]["Authorization"] == "Bearer ide-jwt-token-888"

    # 3. 已登录但 Hub 故障：优雅降级为占位符，仍返回 200
    hub_mode["ok"] = False
    r_deg = client.get(
        "/api/v1/guide/cordis-patch-yml",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert r_deg.status_code == 200
    deg_items = yaml.safe_load(r_deg.text)
    ids_deg = {item["id"]: item for item in deg_items}
    assert ids_deg["mcp-client"]["config"]["servers"]["rgone-hub"]["headers"]["Authorization"] == "Bearer <YOUR_MCP_TOKEN>"


def test_nginx_and_verdaccio_proxy_preserve_encoded_scope():
    """静态配置断言：/npm/ 必须通过 $request_uri 保留 %2f 透传 Verdaccio，禁止 rewrite 解码"""
    nginx_conf = (BASE_DIR / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    verdaccio_conf = (BASE_DIR / "deploy" / "verdaccio" / "config.yaml").read_text(encoding="utf-8")

    assert "resolver 127.0.0.11 valid=30s ipv6=off;" in nginx_conf
    assert "set $rgone_verdaccio verdaccio:4873;" in nginx_conf
    assert "location ^~ /npm/ {" in nginx_conf

    # 截取整个 location ^~ /npm/ 块（包含内层 if 块）
    npm_section = nginx_conf.split("location ^~ /npm/ {", 1)[1].split("location ^~ /market/", 1)[0]
    assert "rewrite " not in npm_section
    assert '$request_uri ~* "^/npm/(.*)$"' in npm_section
    assert "proxy_pass http://$rgone_verdaccio/$npm_raw_path;" in npm_section

    assert "url_prefix: /npm/" in verdaccio_conf
    assert "uplinks: {}" in verdaccio_conf
