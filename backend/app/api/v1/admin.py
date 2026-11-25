from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import encrypt_secret, decrypt_secret
from backend.app.api.deps import get_current_admin
from backend.app.models.admin_user import AdminUser
from backend.app.models.employee import Employee
from backend.app.models.token import UserToken
from backend.app.models.setting import SystemSetting
from backend.app.models.log_cache import UsageLogCache
from backend.app.services.new_api_client import new_api_client, NewApiClient
from backend.app.services.log_sync import LogSyncService, UsageRankingDimension, UsageRankingRange

router = APIRouter(prefix="/admin", tags=["管理员后台接口"])


class SystemSettingsUpdate(BaseModel):
    new_api_base_url: Optional[str] = None
    new_api_access_token: Optional[str] = None
    new_api_user_id: Optional[str] = None
    default_provider_id: Optional[str] = None
    default_provider_name: Optional[str] = None
    default_agent_model: Optional[str] = None
    xiaomishu_api: Optional[str] = None
    xiaomishu_send_user: Optional[str] = None
    xiaomishu_source: Optional[str] = None


class TestGatewayRequest(BaseModel):
    base_url: Optional[str] = None
    access_token: Optional[str] = None
    user_id: Optional[int] = None


@router.get("/overview", summary="管理员总览指标概况")
def get_admin_overview(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """获取全行申领覆盖率、员工数、已签发 Key 数、部门用量排行与最近同步状态"""
    total_employees = db.query(Employee).filter(Employee.is_active.is_(True)).count()
    claimed_tokens = db.query(UserToken).filter(UserToken.status == "active").count()
    disabled_tokens = db.query(UserToken).filter(UserToken.status == "disabled").count()

    claim_rate = 0.0
    if total_employees > 0:
        claim_rate = round((claimed_tokens / total_employees) * 100, 2)

    # 全行累计 Token
    from sqlalchemy import func
    total_tokens_row = db.query(
        func.coalesce(func.sum(UsageLogCache.prompt_tokens + UsageLogCache.completion_tokens), 0)
    ).scalar()
    total_tokens = int(total_tokens_row or 0)

    # 部门排行
    dept_ranking = LogSyncService.get_department_usage_ranking(db)

    # 最近同步状态元数据
    sync_status = db.query(SystemSetting).filter(SystemSetting.key == "last_sync_status").first()
    sync_time = db.query(SystemSetting).filter(SystemSetting.key == "last_sync_time").first()
    sync_msg = db.query(SystemSetting).filter(SystemSetting.key == "last_sync_message").first()

    return {
        "success": True,
        "data": {
            "total_employees": total_employees,
            "claimed_tokens": claimed_tokens,
            "disabled_tokens": disabled_tokens,
            "claim_rate": claim_rate,
            "total_tokens": total_tokens,
            "admin_user": admin.username,
            "department_ranking": dept_ranking,
            "last_sync_status": sync_status.value if sync_status else "never",
            "last_sync_time": sync_time.value if sync_time else "-",
            "last_sync_message": sync_msg.value if sync_msg else "尚未执行同步",
        }
    }


@router.get("/usage/ranking", summary="管理员查看用户与模型 Token 用量排行")
def get_admin_usage_ranking(
    dimension: UsageRankingDimension = "user",
    range: UsageRankingRange = "7d",
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": LogSyncService.get_usage_ranking(db, dimension, range)}


@router.post("/logs/sync", summary="管理员触发网关日志增量同步")
async def admin_sync_logs(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """管理员专属日志增量同步接口，仅持管理员会话可调用"""
    try:
        added = await LogSyncService.sync_incremental_logs(db)
        return {
            "success": True,
            "message": f"网关日志同步成功，本次新增入库 {added} 条记录",
            "added_count": added,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"网关日志同步失败: {str(e)}"
        )


@router.get("/settings", summary="获取全局系统与网关设置")
def get_system_settings(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """读取当前持久化的系统配置"""
    settings_records = db.query(SystemSetting).filter(
        SystemSetting.key != LogSyncService._LOCK_KEY,
        ~SystemSetting.key.startswith("token_claim_", autoescape=True),
    ).all()
    config_dict = {}
    for r in settings_records:
        if r.key == "new_api_access_token" and r.value:
            config_dict[r.key] = decrypt_secret(r.value)
        else:
            config_dict[r.key] = r.value

    return {
        "success": True,
        "data": config_dict
    }


@router.put("/settings", summary="修改全局系统与网关设置")
def update_system_settings(
    update_data: SystemSettingsUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """更新系统配置并同步生效"""
    updates = update_data.model_dump(exclude_unset=True)
    for key, val in updates.items():
        if val is None:
            continue
        record = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not record:
            record = SystemSetting(key=key)
            db.add(record)

        if key == "new_api_access_token":
            record.value = encrypt_secret(val)
        else:
            record.value = str(val)

    db.commit()

    # 同步更新运行时 new-api 客户端配置
    if "new_api_base_url" in updates and updates["new_api_base_url"]:
        new_api_client.base_url = updates["new_api_base_url"].rstrip("/")
    if updates.get("new_api_access_token") is not None:
        new_api_client.access_token = updates["new_api_access_token"].strip()
    if "new_api_user_id" in updates and updates["new_api_user_id"]:
        try:
            new_api_client.user_id = int(updates["new_api_user_id"])
        except ValueError:
            pass

    return {
        "success": True,
        "message": "系统设置已更新"
    }


@router.post("/test-gateway", summary="测试 new-api 网关连通性")
async def test_gateway_connection(
    req: TestGatewayRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """测试指定或当前存储的 new-api 连通性"""
    base_url = req.base_url
    access_token = req.access_token
    user_id = req.user_id

    # 若未指定，从当前 DB 读取
    if not base_url:
        s_url = db.query(SystemSetting).filter(SystemSetting.key == "new_api_base_url").first()
        base_url = s_url.value if s_url else None
    if access_token is None:
        s_token = db.query(SystemSetting).filter(SystemSetting.key == "new_api_access_token").first()
        access_token = decrypt_secret(s_token.value) if s_token and s_token.value else None
    if user_id is None:
        s_uid = db.query(SystemSetting).filter(SystemSetting.key == "new_api_user_id").first()
        if s_uid and s_uid.value:
            try:
                user_id = int(s_uid.value)
            except ValueError:
                user_id = 1

    temp_client = NewApiClient(
        base_url=base_url,
        access_token=access_token,
        user_id=user_id,
        mock=False
    )
    result = await temp_client.test_connection()
    return result
