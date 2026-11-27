from __future__ import annotations
import logging
from datetime import timedelta
from hmac import compare_digest
from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import verify_password, create_access_token, decode_access_token, encrypt_secret
from backend.app.models.admin_user import AdminUser
from backend.app.models.employee import Employee
from backend.app.models.token import UserToken
from backend.app.schemas.auth import (
    EmpLookupRequest,
    EmpLookupResponse,
    EmpVerifyRequest,
    AdminLoginRequest,
    SendCodeRequest,
    SendCodeResponse,
    UnifiedLoginRequest,
    TokenResponse,
)
from backend.app.services.auth_service import AuthService
from backend.app.services.xiaomishu_service import XiaomishuService
from backend.app.services.new_api_client import new_api_client
from backend.app.api.deps import get_client_ip

router = APIRouter(prefix="/auth", tags=["认证与身份核验"])
logger = logging.getLogger("auth")


@router.post("/send-code", response_model=SendCodeResponse, summary="获取登录动态验证码")
async def send_code(
    req: SendCodeRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    输入工号或账号获取验证码：
    1. 若是 admin 管理员，智能感知并告知直接输入密码登录，不发送验证码；
    2. 若是员工工号，校验白名单后调用小秘书接口向员工推送 6 位验证码（5分钟有效，60s防刷冷却）。
    """
    account = req.account.strip()
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入工号或管理账号")

    client_ip = get_client_ip(request)

    # 1. 管理员账号判断
    if account.lower() == "admin" or db.query(AdminUser).filter(AdminUser.username == account).first():
        return SendCodeResponse(
            success=True,
            is_admin=True,
            message="管理员账号无需验证码，请直接输入密码登录",
            cooldown=0
        )

    # 2. 员工白名单校验
    employee = db.query(Employee).filter(
        Employee.emp_no == account,
        Employee.is_active.is_(True)
    ).first()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未检索到工号【{account}】信息，请核对工号或联系管理员导入白名单"
        )

    # 3. 发送小秘书验证码（各 worker 共享存储，无敏感码回传）
    ok, msg = await XiaomishuService.send_verification_code(
        db=db,
        emp_no=employee.emp_no,
        employee_name=employee.name,
        client_ip=client_ip
    )
    if not ok:
        if "频繁" in msg:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return SendCodeResponse(
        success=True,
        is_admin=False,
        message=msg,
        cooldown=60
    )


@router.post("/login", response_model=TokenResponse, summary="统一登录（工号验证码 / 管理员密码）")
async def unified_login(
    req: UnifiedLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    统一登录入口：
    - 管理员：工号/账号为 admin，输入密码直接校验登录
    - 员工：输入工号 + 小秘书收到的 6 位验证码，成功后自动签发/复用专属 API Key 并下发 JWT
    """
    account = req.account.strip()
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入工号或管理账号")

    client_ip = get_client_ip(request)

    # 分支 1：管理员登录
    if account.lower() == "admin" or db.query(AdminUser).filter(AdminUser.username == account).first():
        if not req.password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入管理员密码")

        admin = db.query(AdminUser).filter(
            AdminUser.username == account,
            AdminUser.is_active.is_(True)
        ).first()

        if not admin or not verify_password(req.password, admin.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="管理员用户名或密码错误"
            )

        token = create_access_token({
            "sub": admin.username,
            "role": "admin",
        }, expires_delta=timedelta(hours=settings.ADMIN_JWT_EXPIRE_HOURS))

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ADMIN_JWT_EXPIRE_HOURS * 3600,
            user_type="admin",
            username=admin.username,
        )

    # 分支 2：员工验证码登录
    if not req.code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入 6 位动态验证码")

    employee = db.query(Employee).filter(
        Employee.emp_no == account,
        Employee.is_active.is_(True)
    ).first()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="工号不存在或已被停用"
        )

    # 校验验证码（原子消费与多进程防重放）
    is_valid, msg = XiaomishuService.verify_code(
        db=db,
        emp_no=employee.emp_no,
        input_code=req.code,
        client_ip=client_ip
    )
    if not is_valid:
        if "锁定" in msg:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # 首次登录自动从 new-api 尝试申领专属 Token 并加密存储（解耦设计：网关故障不阻断登录会话）
    if not employee.token:
        try:
            await AuthService.claim_employee_token(db, employee)
        except Exception as e:
            logger.warning(f"员工 {employee.emp_no} 登录时自动申领 Key 未就绪 (网关异常): {e}")

    # 签发 7 天员工 JWT
    jwt_token = create_access_token({
        "sub": employee.emp_no,
        "name": employee.name,
        "department": employee.department,
        "role": "employee",
    }, expires_delta=timedelta(days=settings.JWT_EXPIRE_DAYS))

    return TokenResponse(
        access_token=jwt_token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_DAYS * 86400,
        user_type="employee",
        emp_no=employee.emp_no,
        name=employee.name,
    )


@router.post("/emp/lookup", response_model=EmpLookupResponse, summary="员工工号查验（脱敏核对）")
def emp_lookup(req: EmpLookupRequest, db: Session = Depends(get_db)):
    """
    第一步：员工仅输入工号。
    系统校验是否存在，返回脱敏姓名（如 陈*）与所在部门，绝不泄露全名与 API Key。
    """
    return AuthService.lookup_employee(db, req.emp_no)


@router.post("/emp/verify", response_model=TokenResponse, summary="员工双向精准匹配（已下线）")
async def emp_verify(
    req: EmpVerifyRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    生产环境已下线工号+姓名签发凭证的能力，防止身份冒领。
    返回 403 Forbidden 并引导使用统一登录获取动态验证码。
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="工号+姓名直接登录已停用，请通过统一登录获取小秘书动态验证码"
    )


@router.post("/admin/login", response_model=TokenResponse, summary="管理员账号密码登录")
def admin_login(req: AdminLoginRequest, db: Session = Depends(get_db)):
    """管理员登录接口，签发管理员 JWT 会话凭证"""
    admin = db.query(AdminUser).filter(
        AdminUser.username == req.username.strip(),
        AdminUser.is_active.is_(True)
    ).first()

    if not admin or not verify_password(req.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员用户名或密码错误"
        )

    token = create_access_token({
        "sub": admin.username,
        "role": "admin",
    }, expires_delta=timedelta(hours=settings.ADMIN_JWT_EXPIRE_HOURS))

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ADMIN_JWT_EXPIRE_HOURS * 3600,
        user_type="admin",
        username=admin.username,
    )


class InternalIntrospectRequest(BaseModel):
    token: str


@router.post("/internal/introspect", summary="内部服务调用：核验 JWT 及员工/管理员当前实时有效状态")
def internal_introspect(
    req: InternalIntrospectRequest,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    expected = (settings.CAPABILITY_HUB_INTERNAL_SECRET or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="未配置 CAPABILITY_HUB_INTERNAL_SECRET")
    if not x_internal_secret or not compare_digest(x_internal_secret.strip(), expected):
        raise HTTPException(status_code=403, detail="内部鉴权密钥无效")

    payload = decode_access_token(req.token)
    if not payload:
        return {"active": False, "reason": "invalid_or_expired"}

    role = payload.get("role")
    sub = payload.get("sub")
    if not sub:
        return {"active": False, "reason": "missing_sub"}

    if role == "employee":
        emp = db.query(Employee).filter(Employee.emp_no == sub, Employee.is_active.is_(True)).first()
        if not emp:
            return {"active": False, "reason": "employee_inactive"}
        return {
            "active": True,
            "role": "employee",
            "sub": emp.emp_no,
            "name": emp.name,
            "department": emp.department,
        }

    if role == "admin":
        adm = db.query(AdminUser).filter(AdminUser.username == sub, AdminUser.is_active.is_(True)).first()
        if not adm:
            return {"active": False, "reason": "admin_inactive"}
        return {
            "active": True,
            "role": "admin",
            "sub": adm.username,
            "name": adm.username,
        }

    return {"active": False, "reason": "unsupported_role"}
