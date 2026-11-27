from __future__ import annotations
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.security import decode_access_token
from backend.app.models.employee import Employee
from backend.app.models.admin_user import AdminUser

security_scheme = HTTPBearer(auto_error=False)


def get_client_ip(request: Request) -> str:
    """提取客户端 IP 地址，支持代理透传头"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


async def get_current_employee(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> Employee:
    """获取当前已通过认证的员工主体"""
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少身份凭证，请先完成工号验证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(auth.credentials)
    if not payload or payload.get("role") != "employee":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="凭证无效或已过期，请重新核验工号",
            headers={"WWW-Authenticate": "Bearer"},
        )

    emp_no = payload.get("sub")
    if not emp_no:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效凭证载荷",
            headers={"WWW-Authenticate": "Bearer"},
        )

    employee = db.query(Employee).filter(
        Employee.emp_no == emp_no,
        Employee.is_active.is_(True)
    ).first()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="员工账号不存在或已被停用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return employee


async def get_optional_employee(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Optional[Employee]:
    """可选员工鉴权：未登录或 Token 无效时优雅返回 None，不抛 401"""
    if not auth or not auth.credentials:
        return None
    try:
        payload = decode_access_token(auth.credentials)
    except Exception:
        return None
    if not payload or payload.get("role") != "employee":
        return None
    emp_no = payload.get("sub")
    if not emp_no:
        return None
    return (
        db.query(Employee)
        .filter(Employee.emp_no == emp_no, Employee.is_active.is_(True))
        .first()
    )


async def get_current_admin(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> AdminUser:
    """获取当前已通过认证的后台管理员主体"""
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少管理员身份凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(auth.credentials)
    if not payload or payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，仅管理员可访问此资源",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效管理员凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin = db.query(AdminUser).filter(
        AdminUser.username == username,
        AdminUser.is_active.is_(True)
    ).first()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员账号不存在或已被停用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return admin
