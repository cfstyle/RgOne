from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from cryptography.fernet import Fernet
import jwt
from passlib.context import CryptContext
from backend.app.core.config import settings

# 密码哈希处理
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Fernet 对称加密
_fernet_instance = Fernet(settings.fernet_key)


def encrypt_secret(plaintext: str) -> str:
    """使用 Fernet 对称加密存储敏感内容（API Key、Gateway Token）"""
    if not plaintext:
        return ""
    encrypted = _fernet_instance.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """解密敏感内容"""
    if not ciphertext:
        return ""
    decrypted = _fernet_instance.decrypt(ciphertext.encode("utf-8"))
    return decrypted.decode("utf-8")


def hash_password(password: str) -> str:
    """哈希管理员密码"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验管理员密码"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    payload: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """生成统一 JWT Token"""
    to_encode = payload.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.JWT_EXPIRE_DAYS)
    
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """解码与校验 JWT Token"""
    try:
        decoded = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return decoded
    except Exception:
        return None


def mask_name(name: str) -> str:
    """
    姓名脱敏展示：
    2字：陈飞 -> 陈*
    3字：陈小明 -> 陈*明
    4字及以上：欧阳六六 -> 欧**六
    """
    if not name:
        return ""
    name = name.strip()
    length = len(name)
    if length <= 1:
        return name
    if length == 2:
        return f"{name[0]}*"
    if length == 3:
        return f"{name[0]}*{name[-1]}"
    return f"{name[0]}{'*' * (length - 2)}{name[-1]}"


def mask_key(key: str) -> str:
    """
    API Key 掩码展示：
    sk-abcdef...xyz -> sk-abc...xyz
    """
    if not key:
        return ""
    if len(key) <= 12:
        return "sk-****"
    return f"{key[:7]}...{key[-4:]}"
