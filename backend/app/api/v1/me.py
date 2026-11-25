from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.api.deps import get_current_employee
from backend.app.models.employee import Employee
from backend.app.schemas.auth import EmpTokenDetailResponse
from backend.app.services.auth_service import AuthService

router = APIRouter(prefix="/me", tags=["员工个人工作台"])


@router.get("/token", response_model=EmpTokenDetailResponse, summary="获取当前登录员工的专属 API Key 与网关参数")
def get_my_token(
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """
    返回当前员工的专属 API Key 与网关参数（若网关未申领成功则 status 为 pending_claim）
    """
    return AuthService.get_token_detail(db, current_user)


@router.post("/token/claim", response_model=EmpTokenDetailResponse, summary="员工申领或重试申领专属 API Key")
async def claim_my_token(
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """
    若登录时网关故障或首次申领失败，允许沿用当前已登录会话直接重试申领，无需重新收发验证码。
    """
    await AuthService.claim_employee_token(db, current_user)
    return AuthService.get_token_detail(db, current_user)


@router.post("/token/reset", response_model=EmpTokenDetailResponse, summary="员工自主重置专属 API Key")
async def reset_my_token(
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """
    重新生成 API Key：
    - 调用 new-api 吊销旧 Token 并创建新 Token（保持 token_name 不变，用量数据无缝继承）
    - 本地加密存储新 Key 并递增重置计数
    """
    return await AuthService.reset_token(db, current_user)
