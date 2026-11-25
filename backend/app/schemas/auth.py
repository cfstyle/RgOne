from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class EmpLookupRequest(BaseModel):
    emp_no: str = Field(..., min_length=1, max_length=64, description="员工工号")


class EmpLookupResponse(BaseModel):
    emp_no: str
    department: str
    masked_name: str
    has_key: bool


class EmpVerifyRequest(BaseModel):
    emp_no: str = Field(..., min_length=1, max_length=64, description="员工工号")
    name: str = Field(..., min_length=1, max_length=64, description="员工完整真实姓名")


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="管理员用户名")
    password: str = Field(..., min_length=1, max_length=128, description="管理员密码")


class SendCodeRequest(BaseModel):
    account: str = Field(..., min_length=1, max_length=64, description="工号或管理员账号")


class SendCodeResponse(BaseModel):
    success: bool
    is_admin: bool = False
    message: str
    cooldown: int = 60


class UnifiedLoginRequest(BaseModel):
    account: str = Field(..., min_length=1, max_length=64, description="工号或管理员用户名")
    password: Optional[str] = Field(None, description="管理员登录密码")
    code: Optional[str] = Field(None, description="员工登录动态验证码")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_type: str  # "employee" | "admin"
    emp_no: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None


class EmpTokenDetailResponse(BaseModel):
    emp_no: str
    name: str
    department: str
    token_name: str
    api_key: str
    masked_key: str
    base_url: str
    provider_id: str
    provider_name: str
    api_protocol: str = "OpenAI Chat Completions"
    default_model: str
    status: str = "active"
    reset_count: int
    created_at: str
