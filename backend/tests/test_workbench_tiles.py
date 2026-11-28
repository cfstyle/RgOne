from datetime import datetime

import pytest

from backend.app.core.config import settings
from backend.app.core.security import create_access_token
from backend.app.models.employee import Employee
from backend.app.models.log_cache import UsageLogCache
from backend.app.models.workbench_tile import UserHiddenPresetTile
from backend.app.services import log_sync
from backend.app.services.init_db import seed_workbench_tiles

TILES = "/api/v1/workbench/tiles"
PRESETS = "/api/v1/admin/workbench/presets"


def auth(subject, role="employee"):
    return {"Authorization": f"Bearer {create_access_token({'sub': subject, 'role': role})}"}


@pytest.fixture
def employee():
    return auth("06700956")


@pytest.fixture
def colleague():
    return auth("06701099")


@pytest.fixture
def admin():
    return auth(settings.INIT_ADMIN_USERNAME, "admin")


def prompt(title="测试提示词", **fields):
    return {"title": title, "tile_type": "prompt", "payload": "请总结以下内容。", **fields}


def ids(items):
    return [item["id"] for item in items]


def create(client, endpoint, headers, tile):
    response = client.post(endpoint, headers=headers, json=tile)
    assert response.status_code == 201, response.text
    return response.json()


def test_initial_presets(client, db_session, admin):
    initial = client.get(PRESETS, headers=admin).json()
    assert {tile["title"] for tile in initial} >= {
        "SQL 调优专家", "制度条款提炼", "周报汇报润色", "能力中心 (MCP)",
    }
    assert all(tile["owner_emp_no"] is None for tile in initial)
    assert any(tile["tile_type"] == "link" and tile["payload"] == "/capabilities" for tile in initial)
    seed_workbench_tiles(db_session)
    db_session.commit()
    assert client.get(PRESETS, headers=admin).json() == initial


def test_admin_preset_lifecycle(client, admin, employee):
    assert client.get(PRESETS).status_code == 401
    assert client.get(PRESETS, headers=employee).status_code == 403
    assert client.post(PRESETS, headers=employee, json=prompt()).status_code == 403
    assert client.get(TILES, headers=admin).status_code == 401
    preset = create(client, PRESETS, admin, prompt(icon="Database", sort_order=-30))
    tile_id = preset["id"]
    path = f"{PRESETS}/{tile_id}"
    assert preset["owner_emp_no"] is None and preset["is_enabled"] is True
    assert client.get(PRESETS, headers=admin).json()[0]["id"] == tile_id
    assert client.get(TILES, headers=employee).json()["tiles"][0]["id"] == tile_id
    assert client.patch(path, headers=employee, json={"title": "越权编辑"}).status_code == 403
    edited = client.patch(path, headers=admin, json={"subtitle": "测试描述", "is_enabled": False})
    assert edited.status_code == 200
    assert edited.json()["subtitle"] == "测试描述"
    assert tile_id not in ids(client.get(TILES, headers=employee).json()["tiles"])
    assert tile_id in ids(client.get(PRESETS, headers=admin).json())
    assert client.patch(path, headers=admin, json={"is_enabled": True}).status_code == 200
    assert tile_id in ids(client.get(TILES, headers=employee).json()["tiles"])
    assert client.delete(path, headers=admin).status_code == 204
    assert tile_id not in ids(client.get(PRESETS, headers=admin).json())


def test_personal_crud_and_ownership(client, employee, colleague, admin):
    assert client.get(TILES).status_code == 401
    assert client.post(TILES, headers=employee, json=prompt(owner_emp_no="06701099")).status_code == 422
    personal = create(client, TILES, employee, prompt())
    assert personal["owner_emp_no"] == "06700956"
    assert personal["sort_order"] == 0 and personal["created_at"] and personal["updated_at"]
    tile_id = personal["id"]
    path = f"{TILES}/{tile_id}"
    assert tile_id in ids(client.get(TILES, headers=employee).json()["tiles"])
    assert tile_id not in ids(client.get(TILES, headers=colleague).json()["tiles"])
    assert client.patch(path, headers=employee, json={"title": "已修改", "category": "开发"}).json()["title"] == "已修改"
    assert client.patch(path, headers=employee, json={"category": None}).json()["category"] is None
    assert client.patch(path, headers=employee, json={"title": None}).status_code == 422
    assert client.patch(path, headers=colleague, json={"title": "越权"}).status_code == 404
    assert client.delete(path, headers=colleague).status_code == 404
    assert client.patch(f"{PRESETS}/{tile_id}", headers=admin, json={"title": "越权"}).status_code == 404
    assert client.delete(f"{PRESETS}/{tile_id}", headers=admin).status_code == 404
    preset_id = client.get(PRESETS, headers=admin).json()[0]["id"]
    assert client.patch(f"{TILES}/{preset_id}", headers=employee, json={"title": "越权"}).status_code == 404
    assert client.delete(f"{TILES}/{preset_id}", headers=employee).status_code == 404
    assert client.delete(path, headers=employee).status_code == 204
    assert tile_id not in ids(client.get(TILES, headers=employee).json()["tiles"])


def test_hide_restore_and_delete_cleanup(client, db_session, employee, colleague, admin):
    preset = create(client, PRESETS, admin, prompt())
    tile_id = preset["id"]
    path = f"/api/v1/workbench/presets/{tile_id}/hide"
    for _ in range(2):
        assert client.post(path, headers=employee).status_code == 204
    mine = client.get(TILES, headers=employee).json()
    assert tile_id not in ids(mine["tiles"])
    assert ids(mine["hidden_presets"]).count(tile_id) == 1
    assert tile_id in ids(client.get(TILES, headers=colleague).json()["tiles"])
    assert client.delete(path, headers=colleague).status_code == 204
    assert tile_id in ids(client.get(TILES, headers=employee).json()["hidden_presets"])
    for _ in range(2):
        assert client.delete(path, headers=employee).status_code == 204
    mine = client.get(TILES, headers=employee).json()
    assert tile_id in ids(mine["tiles"]) and tile_id not in ids(mine["hidden_presets"])
    assert client.post(path, headers=employee).status_code == 204
    assert client.delete(f"{PRESETS}/{tile_id}", headers=admin).status_code == 204
    assert db_session.query(UserHiddenPresetTile).filter_by(tile_id=tile_id).count() == 0


def test_reorder_is_atomic_and_personal(client, employee, admin):
    first = create(client, TILES, employee, prompt("甲"))
    second = create(client, TILES, employee, prompt("乙"))
    preset_id = client.get(PRESETS, headers=admin).json()[0]["id"]
    reorder = f"{TILES}/reorder"
    new_items = [{"id": first["id"], "sort_order": 20}, {"id": second["id"], "sort_order": 10}]
    assert client.post(reorder, headers=employee, json={"items": [new_items[0], {
        "id": preset_id, "sort_order": -1,
    }]}).status_code == 404
    visible = client.get(TILES, headers=employee).json()["tiles"]
    assert next(tile for tile in visible if tile["id"] == first["id"])["sort_order"] == 0
    assert client.post(reorder, headers=employee, json={"items": [new_items[0]] * 2}).status_code == 422
    assert client.post(reorder, headers=employee, json={"items": new_items}).status_code == 204
    visible = client.get(TILES, headers=employee).json()["tiles"]
    assert ids(visible[-2:]) == [second["id"], first["id"]]
    hide_personal = f"/api/v1/workbench/presets/{first['id']}/hide"
    assert client.post(hide_personal, headers=employee).status_code == 404
    for tile in (first, second):
        assert client.delete(f"{TILES}/{tile['id']}", headers=employee).status_code == 204


@pytest.mark.parametrize("url", [
    " javascript:alert(1)", "data:text/html,example", "//example.test", "/\\example.test",
    "/\texample.test", "https:///example.test", "https://name@example.test",
])
def test_links_reject_unsafe_targets(client, employee, admin, url):
    draft = prompt(tile_type="link", payload=url)
    assert client.post(TILES, headers=employee, json=draft).status_code == 422
    assert client.post(PRESETS, headers=admin, json=draft).status_code == 422


def test_patch_validates_final_tile_type_and_payload(client, employee):
    tile = create(client, TILES, employee, prompt(payload="javascript:alert(1)"))
    path = f"{TILES}/{tile['id']}"
    assert client.patch(path, headers=employee, json={"tile_type": "link"}).status_code == 422
    assert client.patch(path, headers=employee, json={"icon": "Arbitrary"}).status_code == 422
    for url in ("/capabilities?tab=mine", "https://example.test/path", "http://example.test:8080/"):
        changed = client.patch(path, headers=employee, json={"tile_type": "link", "payload": url})
        assert changed.status_code == 200
        assert changed.json()["payload"] == url
    assert client.patch(path, headers=employee, json={"payload": " JAVASCRIPT:alert(1)"}).status_code == 422
    assert client.delete(path, headers=employee).status_code == 204


def test_month_kpi_uses_shanghai_calendar(client, db_session, monkeypatch):
    employee = Employee(emp_no="phase3a-kpi-test", name="工作台统计测试员工")

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            local = datetime(2026, 11, 2, 0, 30, tzinfo=log_sync.SHANGHAI_TIME)
            return local.astimezone(tz)

    def log(identity, month, day):
        return UsageLogCache(
            emp_no=employee.emp_no, new_api_log_id=identity, token_name="test", model_name="test",
            prompt_tokens=10, completion_tokens=2,
            created_at=int(datetime(2026, month, day, 0, 5, tzinfo=log_sync.SHANGHAI_TIME).timestamp()),
        )

    rows = [log(93001, 10, 31), log(93002, 11, 1), log(93003, 11, 2)]
    db_session.add_all([employee, *rows])
    db_session.commit()
    monkeypatch.setattr(log_sync, "datetime", FixedDateTime)
    try:
        for period, expected in (("today", 1), ("month", 2)):
            response = client.get(f"/api/v1/me/usage/overview?range={period}", headers=auth(employee.emp_no))
            assert response.status_code == 200
            assert response.json()["data"]["total_requests"] == expected
            assert response.json()["data"]["total_tokens"] == expected * 12
    finally:
        for row in rows:
            db_session.delete(row)
        db_session.delete(employee)
        db_session.commit()
