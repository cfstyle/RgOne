from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

import httpx
import jwt
from fastapi.testclient import TestClient
from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.employee import Employee
from backend.app.services.hub_client import CapabilityHubClient


def test_rgone_jwt_contains_issuer_and_internal_introspect(client: TestClient, db_session, monkeypatch):
    """验证 RgOne 签发的 JWT 含 iss='rgone'，且内部 /auth/internal/introspect 实时核验员工状态"""
    monkeypatch.setattr(settings, "CAPABILITY_HUB_INTERNAL_SECRET", "rgone-hub-secret-test")

    emp = db_session.query(Employee).filter(Employee.emp_no == "06700956").first()
    assert emp is not None
    emp.is_active = True
    db_session.commit()

    token = create_access_token({
        "sub": emp.emp_no,
        "name": emp.name,
        "department": emp.department,
        "role": "employee",
    })
    decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert decoded["iss"] == "rgone"
    assert decoded["role"] == "employee"
    assert decoded["sub"] == "06700956"

    # 1. 错误内部密钥拒绝
    r_bad = client.post(
        "/api/v1/auth/internal/introspect",
        json={"token": token},
        headers={"X-Internal-Secret": "wrong"},
    )
    assert r_bad.status_code == 403

    # 2. 在职状态核验通过
    r_ok = client.post(
        "/api/v1/auth/internal/introspect",
        json={"token": token},
        headers={"X-Internal-Secret": "rgone-hub-secret-test"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["active"] is True
    assert r_ok.json()["sub"] == "06700956"

    # 3. 员工被停用后，即使 JWT 未过期也实时返回 active=False
    emp.is_active = False
    db_session.commit()
    r_inactive = client.post(
        "/api/v1/auth/internal/introspect",
        json={"token": token},
        headers={"X-Internal-Secret": "rgone-hub-secret-test"},
    )
    assert r_inactive.status_code == 200
    assert r_inactive.json()["active"] is False
    assert r_inactive.json()["reason"] == "employee_inactive"

    # 还原状态
    emp.is_active = True
    db_session.commit()


def test_employee_disable_syncs_and_retries_capability_hub(client: TestClient, db_session, monkeypatch):
    """验证停用/复职员工联动同步 Capability Hub，失败记录 hub_revoke_pending 并支持重试恢复"""
    adm_token = create_access_token({"sub": settings.INIT_ADMIN_USERNAME, "role": "admin"})
    adm_headers = {"Authorization": f"Bearer {adm_token}"}

    emp_no = "06709988"
    existing = db_session.query(Employee).filter(Employee.emp_no == emp_no).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    r_create = client.post(
        "/api/v1/admin/employees",
        json={"emp_no": emp_no, "name": "联动测试", "department": "金融科技部", "is_active": True},
        headers=adm_headers,
    )
    assert r_create.status_code == 200
    emp_id = r_create.json()["id"]

    monkeypatch.setattr(settings, "CAPABILITY_HUB_BASE_URL", "http://mock-hub.internal:8080")
    monkeypatch.setattr(settings, "CAPABILITY_HUB_INTERNAL_SECRET", "hub-sync-secret")

    called_urls = []
    hub_should_fail = {"flag": True}

    original_post = httpx.AsyncClient.post

    async def mock_hub_post(self, url, *args, **kwargs):
        if "mock-hub.internal" in str(url):
            called_urls.append(str(url))
            if hub_should_fail["flag"]:
                return httpx.Response(status_code=503, json={"detail": "Hub restarting"})
            return httpx.Response(status_code=200, json={"emp_no": emp_no, "is_active": "restore" in str(url)})
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_hub_post)

    # 1. 模拟 Hub 短暂不可用时停用员工：本地停用生效，并标记 hub_revoke_pending
    r_disable = client.put(f"/api/v1/admin/employees/{emp_id}", json={"is_active": False}, headers=adm_headers)
    assert r_disable.status_code == 200
    assert "待重试" in r_disable.json()["message"]
    assert any(u.endswith(f"/internal/users/{emp_no}/revoke") for u in called_urls)

    row = [x for x in client.get(f"/api/v1/admin/employees?keyword={emp_no}", headers=adm_headers).json()["items"] if x["id"] == emp_id][0]
    assert row["is_active"] is False
    assert row["hub_sync_status"] == "hub_revoke_pending"

    # 2. 恢复 Hub 可达后点击重试同步
    hub_should_fail["flag"] = False
    r_retry = client.post(f"/api/v1/admin/employees/{emp_id}/retry-hub-sync", headers=adm_headers)
    assert r_retry.status_code == 200

    row_synced = [x for x in client.get(f"/api/v1/admin/employees?keyword={emp_no}", headers=adm_headers).json()["items"] if x["id"] == emp_id][0]
    assert row_synced["hub_sync_status"] == "synced"

    # 3. 复职同步 restore
    r_restore = client.put(f"/api/v1/admin/employees/{emp_id}", json={"is_active": True}, headers=adm_headers)
    assert r_restore.status_code == 200
    assert any(u.endswith(f"/internal/users/{emp_no}/restore") for u in called_urls)

    # 4. 删除前若 Hub 吊销失败，必须中止删除防止残留权限
    hub_should_fail["flag"] = True
    r_del_fail = client.delete(f"/api/v1/admin/employees/{emp_id}", headers=adm_headers)
    assert r_del_fail.status_code == 502

    # 5. Hub 恢复后允许彻底删除
    hub_should_fail["flag"] = False
    r_del_ok = client.delete(f"/api/v1/admin/employees/{emp_id}", headers=adm_headers)
    assert r_del_ok.status_code == 200
