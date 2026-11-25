from __future__ import annotations
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from hashlib import sha256
import logging
import math
from typing import Optional, Tuple
from uuid import uuid4
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.security import (
    encrypt_secret,
    decrypt_secret,
    mask_name,
    mask_key,
    create_access_token,
)
from backend.app.models.employee import Employee
from backend.app.models.token import UserToken
from backend.app.models.auth_lockout import AuthLockout
from backend.app.models.setting import SystemSetting
from backend.app.services.new_api_client import TokenCreationRejected, new_api_client


logger = logging.getLogger(__name__)


class AuthService:
    """员工身份核验、锁表限流与 Token 签发核心服务"""

    _CLAIM_LEASE_DURATION = timedelta(minutes=2)

    @staticmethod
    def _check_and_raise_lockout(db: Session, target_type: str, target_val: str):
        """检查目标是否处于输错锁定状态"""
        now = datetime.utcnow()
        lock = db.query(AuthLockout).filter(
            AuthLockout.target_type == target_type,
            AuthLockout.target_val == target_val
        ).first()

        if lock and lock.locked_until and lock.locked_until > now:
            remain_sec = int((lock.locked_until - now).total_seconds())
            remain_min = max(1, math.ceil(remain_sec / 60))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"连续多次验证失败，该账号/IP 已被锁定保护，请在 {remain_min} 分钟后再试"
            )

    @staticmethod
    def _record_failure(db: Session, target_type: str, target_val: str) -> int:
        """记录一次失败，若达到阈值则执行锁定"""
        now = datetime.utcnow()
        lock = db.query(AuthLockout).filter(
            AuthLockout.target_type == target_type,
            AuthLockout.target_val == target_val
        ).first()

        if not lock:
            lock = AuthLockout(
                target_type=target_type,
                target_val=target_val,
                fail_count=1,
                updated_at=now
            )
            db.add(lock)
            db.commit()
            return 1

        # 若已过锁定期，重置计数
        if lock.locked_until and lock.locked_until <= now:
            lock.fail_count = 1
            lock.locked_until = None
        else:
            lock.fail_count += 1

        if lock.fail_count >= settings.AUTH_MAX_FAILURES:
            lock.locked_until = now + timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)

        lock.updated_at = now
        db.commit()
        return lock.fail_count

    @staticmethod
    def _clear_failure(db: Session, target_type: str, target_val: str):
        """验证成功，清除失败记录"""
        db.query(AuthLockout).filter(
            AuthLockout.target_type == target_type,
            AuthLockout.target_val == target_val
        ).delete()
        db.commit()

    @classmethod
    def lookup_employee(cls, db: Session, emp_no: str) -> dict:
        """
        工号快速查验：仅返回部门与脱敏姓名（如 陈*），绝不泄露全名与 Key
        """
        emp_no = emp_no.strip()
        employee = db.query(Employee).filter(
            Employee.emp_no == emp_no,
            Employee.is_active.is_(True)
        ).first()

        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未检索到该工号信息，请核对后重试或联系系统管理员导入"
            )

        has_key = employee.token is not None and employee.token.status == "active"
        return {
            "emp_no": employee.emp_no,
            "department": employee.department,
            "masked_name": mask_name(employee.name),
            "has_key": has_key,
        }

    @classmethod
    async def verify_employee(
        cls,
        db: Session,
        emp_no: str,
        name: str,
        client_ip: str = "127.0.0.1"
    ) -> Tuple[str, Employee]:
        """
        生产环境中已彻底关闭工号+姓名签发凭证的能力。
        统一要求使用小秘书动态验证码进行登录。
        """
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="工号+姓名直接登录已停用，请通过统一登录获取小秘书动态验证码"
        )

    @classmethod
    async def claim_employee_token(cls, db: Session, employee: Employee) -> UserToken:
        """首次申领与补领使用同一个跨 worker 的签发租约。"""
        emp_no = employee.emp_no
        emp_digest = urlsafe_b64encode(sha256(emp_no.encode("utf-8")).digest()).decode("ascii").rstrip("=")
        lock_key = f"token_claim_lock:{emp_digest}"
        pending_key = f"token_claim_pending:{emp_digest}"
        owner = uuid4().hex
        now = datetime.utcnow()
        busy = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前 Key 正在申领，请稍后刷新")

        lease = db.query(SystemSetting).filter(SystemSetting.key == lock_key)
        taken_over = lease.filter(SystemSetting.updated_at <= now - cls._CLAIM_LEASE_DURATION).update(
            {"value": owner, "updated_at": now}, synchronize_session=False
        )
        if not taken_over:
            if lease.first():
                db.rollback()
                raise busy
            db.add(SystemSetting(key=lock_key, value=owner, updated_at=now))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise busy from None

        def require_lease():
            renewed_at = datetime.utcnow()
            renewed = lease.filter(
                SystemSetting.value == owner,
                SystemSetting.updated_at > renewed_at - cls._CLAIM_LEASE_DURATION,
            ).update({"updated_at": renewed_at}, synchronize_session=False)
            if renewed != 1:
                raise busy

        try:
            if not employee.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="该员工账号已被管理员停用，无法申领或使用 API Key"
                )
            if employee.token:
                if employee.token.status == "active" and employee.token.api_key_encrypted:
                    return employee.token
                if employee.token.status == "disabled":
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该 API Key 已被管理员禁用")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有凭证，请通过重置入口恢复")

            pending = db.get(SystemSetting, pending_key)
            pending_name = pending.value if pending else None
            token_name = pending_name or f"EMP_{emp_no}_{employee.name}"
            db.commit()
            gateway_token = await new_api_client.get_token_by_name(token_name, clean_duplicates=False)
            token_id = gateway_token.get("id") if gateway_token else None
            raw_key = (gateway_token.get("key") or "").strip() if gateway_token else ""
            if not token_id or not raw_key or "*" in raw_key:
                if pending_name:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="上次 Key 签发结果尚未确认，请稍后重试查询"
                    )
                if gateway_token is not None:
                    if not token_id:
                        raise RuntimeError("网关返回的同名 Token 缺少 ID")
                    require_lease()
                    db.commit()
                    if not await new_api_client.delete_token(token_id):
                        raise RuntimeError("无法确认旧 Token 已删除")

                # 调用 POST 前持久化待核对状态。超时或 worker 退出时，重试只核对签发结果。
                require_lease()
                db.add(SystemSetting(key=pending_key, value=token_name))
                db.commit()
                try:
                    gateway_token = await new_api_client.create_token(token_name)
                except TokenCreationRejected:
                    require_lease()
                    db.query(SystemSetting).filter_by(key=pending_key).delete(synchronize_session=False)
                    db.commit()
                    raise
                token_id = gateway_token.get("id")
                raw_key = (gateway_token.get("key") or "").strip()
                if not token_id or not raw_key or "*" in raw_key:
                    raise RuntimeError("网关未返回有效的明文 API Key 凭证")

            require_lease()
            if not employee.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="该员工账号已被管理员停用，无法申领或使用 API Key"
                )
            user_token = UserToken(
                emp_no=emp_no,
                new_api_token_id=token_id,
                token_name=token_name,
                api_key_encrypted=encrypt_secret(raw_key),
                status="active",
                reset_count=0
            )
            db.add(user_token)
            db.query(SystemSetting).filter_by(key=pending_key).delete(synchronize_session=False)
            db.commit()
            return user_token
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("员工 Key 申领失败 (%s)", type(e).__name__)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="网关服务异常或签发结果未确认，API Key 申领未完成"
            ) from None
        finally:
            db.rollback()
            try:
                lease.filter(SystemSetting.value == owner).delete(synchronize_session=False)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning("释放员工 Key 申领锁失败 (%s)", type(e).__name__)

    @classmethod
    def get_token_detail(cls, db: Session, employee: Employee) -> dict:
        """获取当前员工解密后的专属 API Key 与完整网关配置"""
        if not employee.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="该员工账号已被管理员停用，无法查看或使用 API Key"
            )

        # 读取动态网关配置（若数据库有更新优先从 DB 读）
        gw_url_setting = db.query(SystemSetting).filter(SystemSetting.key == "new_api_base_url").first()
        base_url = gw_url_setting.value if gw_url_setting and gw_url_setting.value else settings.NEW_API_BASE_URL
        if not base_url.endswith("/v1"):
            base_url = f"{base_url.rstrip('/')}/v1"

        provider_id_setting = db.query(SystemSetting).filter(SystemSetting.key == "default_provider_id").first()
        provider_id = provider_id_setting.value if provider_id_setting and provider_id_setting.value else settings.DEFAULT_PROVIDER_ID

        provider_name_setting = db.query(SystemSetting).filter(SystemSetting.key == "default_provider_name").first()
        provider_name = provider_name_setting.value if provider_name_setting and provider_name_setting.value else settings.DEFAULT_PROVIDER_NAME

        agent_model_setting = db.query(SystemSetting).filter(SystemSetting.key == "default_agent_model").first()
        default_model = agent_model_setting.value if agent_model_setting and agent_model_setting.value else settings.DEFAULT_AGENT_MODEL

        # 若尚未申领或网关此前未成功申领
        if not employee.token:
            return {
                "emp_no": employee.emp_no,
                "name": employee.name,
                "department": employee.department,
                "token_name": f"EMP_{employee.emp_no}_{employee.name}",
                "api_key": "",
                "masked_key": "Key 暂未申领成功，请点击重新申领",
                "base_url": base_url,
                "provider_id": provider_id,
                "provider_name": provider_name,
                "api_protocol": "OpenAI Chat Completions",
                "default_model": default_model,
                "status": "pending_claim",
                "reset_count": 0,
                "created_at": "-",
            }

        if employee.token.status == "pending_reset" or not employee.token.api_key_encrypted:
            raw_key = "PENDING_RESET_PLEASE_RETRY"
            masked_k = "重置待恢复，请点击重试"
        else:
            raw_key = decrypt_secret(employee.token.api_key_encrypted)
            masked_k = mask_key(raw_key)

        return {
            "emp_no": employee.emp_no,
            "name": employee.name,
            "department": employee.department,
            "token_name": employee.token.token_name,
            "api_key": raw_key,
            "masked_key": masked_k,
            "base_url": base_url,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "api_protocol": "OpenAI Chat Completions",
            "default_model": default_model,
            "status": employee.token.status,
            "reset_count": employee.token.reset_count,
            "created_at": employee.token.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    async def perform_token_reset(
        cls,
        db: Session,
        user_token: UserToken,
        is_admin: bool = False
    ) -> UserToken:
        """
        统一执行 Token 重置核心事务：
        - 员工重置与管理员重置复用同一套逻辑
        - 管理员禁用后，员工自助重置抛出 403 明确拒绝
        - 旧 Key 删除失败时停止签发
        - 旧 Key 已删除而新 Key 创建失败时，保持 pending_reset 可恢复状态，允许安全重试
        - 签发成功必须取得有效 ID 和非掩码明文 Key
        - 保持原 token_name 保证历史用量连续性
        """
        if not is_admin and user_token.status == "disabled":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="该 API Key 已被管理员禁用，无法自助重置，请联系管理员处理"
            )

        # 原子 CAS 锁定状态为 resetting，防止并发争抢导致多个网关 Key 冲突
        token_id = user_token.id
        prior_status = user_token.status
        allowed_statuses = ["active", "pending_reset"] if not is_admin else ["active", "pending_reset", "disabled"]

        now_utc = datetime.utcnow()
        lock_timeout = now_utc - timedelta(seconds=30)

        # 尝试 CAS 锁定：目标状态处于正常可用/待恢复状态，或处于已超时的僵尸 resetting 状态（支持 worker 崩溃恢复）
        row_count = db.query(UserToken).filter(
            UserToken.id == token_id,
            (
                UserToken.status.in_(allowed_statuses) |
                ((UserToken.status == "resetting") & (UserToken.updated_at < lock_timeout))
            )
        ).update({"status": "resetting", "updated_at": now_utc}, synchronize_session=False)
        db.commit()

        if row_count == 0:
            db.refresh(user_token)
            if user_token.status == "resetting":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="当前 Key 正在重置中，请勿重复提交"
                )
            if not is_admin and user_token.status == "disabled":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="该 API Key 已被管理员禁用，无法自助重置，请联系管理员处理"
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="当前状态无法重置，请稍后刷新重试"
            )

        token_name = user_token.token_name
        old_token_id = user_token.new_api_token_id

        # 1. 尝试删除旧 Token（若不是处于已删除旧 Token 的 pending_reset 状态）
        if prior_status != "pending_reset" and old_token_id:
            try:
                if not await new_api_client.delete_token(old_token_id):
                    raise RuntimeError("无法确认旧 Token 已删除")
            except Exception as e:
                # 恢复原状态并提交
                db.query(UserToken).filter(UserToken.id == token_id).update(
                    {"status": prior_status, "updated_at": datetime.utcnow()}, synchronize_session=False
                )
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"网关吊销旧 API Key 失败，已中止重置操作: {str(e)}"
                )

            # 旧 Key 成功删除后，清空旧 ID，但状态继续保持独占 resetting，严禁提前释放锁！
            db.query(UserToken).filter(UserToken.id == token_id).update(
                {"new_api_token_id": None, "updated_at": datetime.utcnow()}, synchronize_session=False
            )
            db.commit()

        # 2. 调用网关签发同名新 Token（持锁独占调用，绝无第二者插队）
        try:
            # 接管超时/僵尸任务或异常恢复时，先核对网关上一次签发结果
            existing_gw_token = None
            if prior_status in ("resetting", "pending_reset") or not old_token_id:
                existing_gw_token = await new_api_client.get_token_by_name(token_name)

            if existing_gw_token and existing_gw_token.get("id") and existing_gw_token.get("key") and "*" not in existing_gw_token.get("key"):
                new_id = existing_gw_token["id"]
                raw_key = existing_gw_token["key"]
            else:
                if existing_gw_token and existing_gw_token.get("id"):
                    if not await new_api_client.delete_token(existing_gw_token["id"]):
                        raise RuntimeError("无法确认旧 Token 已删除")
                new_data = await new_api_client.create_token(token_name)
                raw_key = new_data.get("key", "").strip()
                new_id = new_data.get("id")

            if not new_id or not raw_key or "*" in raw_key:
                raise ValueError("网关未返回有效的明文 API Key 凭证")

            user_token.new_api_token_id = new_id
            user_token.api_key_encrypted = encrypt_secret(raw_key)
            user_token.status = "active"
            user_token.reset_count += 1
            user_token.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user_token)
            return user_token
        except Exception as e:
            # 新 Key 签发失败，状态转移至 pending_reset，供后续重试恢复
            db.query(UserToken).filter(UserToken.id == token_id).update(
                {"new_api_token_id": None, "status": "pending_reset", "updated_at": datetime.utcnow()}, synchronize_session=False
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"旧 Key 已吊销，但网关签发新 Key 失败: {str(e)}。当前凭证处于待恢复状态，请重试以完成重置"
            )

    @classmethod
    async def reset_token(cls, db: Session, employee: Employee) -> dict:
        """员工自助重置专属 Key"""
        if not employee.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="该员工账号已被管理员停用，无法重置 API Key"
            )
        if not employee.token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到原有 Token 记录"
            )
        await cls.perform_token_reset(db=db, user_token=employee.token, is_admin=False)
        return cls.get_token_detail(db, employee)
