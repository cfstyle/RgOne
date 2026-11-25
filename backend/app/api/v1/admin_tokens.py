from __future__ import annotations
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import mask_key, encrypt_secret, decrypt_secret
from backend.app.api.deps import get_current_admin
from backend.app.models.token import UserToken
from backend.app.models.employee import Employee
from backend.app.models.log_cache import UsageLogCache
from backend.app.models.admin_user import AdminUser
from backend.app.services.new_api_client import new_api_client
from backend.app.services.auth_service import AuthService

router = APIRouter(prefix="/admin/tokens", tags=["管理员 API Key 运维管理"])


class TokenStatusUpdate(BaseModel):
    status: str  # "active" 或 "disabled"


@router.get("", summary="分页获取全行员工 API Key 列表与用量汇总")
def list_tokens(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(UserToken).join(Employee, UserToken.emp_no == Employee.emp_no)
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.filter((UserToken.emp_no.ilike(kw)) | (UserToken.token_name.ilike(kw)) | (Employee.name.ilike(kw)))
    if status_filter:
        query = query.filter(UserToken.status == status_filter)

    total = query.count()
    tokens = query.order_by(UserToken.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for t in tokens:
        raw_key = decrypt_secret(t.api_key_encrypted)
        # 统计历史用量
        usage_stat = db.query(
            func.count(UsageLogCache.id).label("requests"),
            func.sum(UsageLogCache.prompt_tokens + UsageLogCache.completion_tokens).label("total_tokens")
        ).filter(UsageLogCache.emp_no == t.emp_no).first()

        req_count = int(usage_stat.requests or 0)
        tok_count = int(usage_stat.total_tokens or 0)

        items.append({
            "id": t.id,
            "emp_no": t.emp_no,
            "employee_name": t.employee.name if t.employee else "",
            "department": t.employee.department if t.employee else "",
            "token_name": t.token_name,
            "new_api_token_id": t.new_api_token_id,
            "masked_key": mask_key(raw_key),
            "status": t.status,
            "reset_count": t.reset_count,
            "total_requests": req_count,
            "total_tokens": tok_count,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.put("/{token_id}/status", summary="启用/禁用员工 Key")
async def toggle_token_status(
    token_id: int,
    data: TokenStatusUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    t = db.query(UserToken).filter(UserToken.id == token_id).first()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token 记录未找到")

    target_status = data.status.lower()
    if target_status not in ("active", "disabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="状态值必须为 active 或 disabled")

    # 同步 new-api 网关：仅在网关确认成功后才更新本地状态
    if t.new_api_token_id:
        api_status = 1 if target_status == "active" else 2
        try:
            await new_api_client.update_token_status(t.new_api_token_id, api_status)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"网关更新 Token 状态失败，已取消本地修改: {str(e)}"
            )

    t.status = target_status
    t.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": f"API Key 已切换为 {target_status} 状态"}


@router.post("/{token_id}/reset", summary="管理员强制重置员工 Key")
async def force_reset_token(
    token_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    t = db.query(UserToken).filter(UserToken.id == token_id).first()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token 记录未找到")

    # 复用统一重置事务逻辑
    updated_token = await AuthService.perform_token_reset(db=db, user_token=t, is_admin=True)
    raw_key = decrypt_secret(updated_token.api_key_encrypted)

    return {
        "success": True,
        "message": "API Key 已强制重置",
        "new_masked_key": mask_key(raw_key)
    }
