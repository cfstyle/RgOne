from __future__ import annotations
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.setting import SystemSetting
from backend.app.models.verification_code import VerificationCode
from backend.app.services.auth_service import AuthService

logger = logging.getLogger("xiaomishu")


class XiaomishuService:
    """小秘书即时消息推送与动态验证码管理服务（多进程共享、安全哈希与原子消费）"""

    @classmethod
    def _hash_code(cls, emp_no: str, code: str) -> str:
        """使用 SHA-256 计算验证码的安全摘要，防止数据库直接暴露明文"""
        salt = settings.APP_SECRET_KEY or "rgone_secret_salt_2026"
        data = f"{salt}:{emp_no}:{code.strip()}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def _get_config(cls, db: Optional[Session] = None) -> Tuple[str, str, str]:
        """优先从数据库 SystemSetting 获取动态配置，缺省使用环境变量"""
        api_url = settings.XIAOMISHU_API or ""
        send_user = settings.XIAOMISHU_SEND_USER or ""
        source = settings.XIAOMISHU_SOURCE or "金融市场部RPA"

        if db is not None:
            try:
                url_rec = db.query(SystemSetting).filter(SystemSetting.key == "xiaomishu_api").first()
                if url_rec and url_rec.value:
                    api_url = url_rec.value.strip()

                user_rec = db.query(SystemSetting).filter(SystemSetting.key == "xiaomishu_send_user").first()
                if user_rec and user_rec.value:
                    send_user = user_rec.value.strip()

                src_rec = db.query(SystemSetting).filter(SystemSetting.key == "xiaomishu_source").first()
                if src_rec and src_rec.value:
                    source = src_rec.value.strip()
            except Exception as e:
                logger.warning(f"读取数据库小秘书配置异常: {e}")

        return api_url, send_user, source

    @classmethod
    async def send_verification_code(
        cls,
        db: Session,
        emp_no: str,
        employee_name: str = "",
        client_ip: str = "127.0.0.1"
    ) -> Tuple[bool, str]:
        """
        生成 6 位动态验证码并通过小秘书推送
        - 使用 secrets 生成随机码
        - 60s 冷却与 5 分钟有效时间持久化到各 worker 共享的 SQLite 存储
        - 推送确认成功后才允许登录，日志与响应均不暴露验证码
        """
        emp_no = emp_no.strip()

        # 检查工号与 IP 是否处于输错锁定状态
        AuthService._check_and_raise_lockout(db, "emp_no", emp_no)
        AuthService._check_and_raise_lockout(db, "ip", client_ip)

        now_utc = datetime.utcnow()

        # 60 秒发送冷却检查（查询最近一条已发出的验证码）
        latest_code = db.query(VerificationCode).filter(
            VerificationCode.emp_no == emp_no
        ).order_by(VerificationCode.id.desc()).first()

        if latest_code and latest_code.sent_at:
            cooldown_limit = latest_code.sent_at + timedelta(seconds=60)
            if now_utc < cooldown_limit:
                remain_sec = int((cooldown_limit - now_utc).total_seconds())
                remain = max(1, remain_sec)
                return False, f"验证码获取过于频繁，请等待 {remain} 秒后再试"

        api_url, default_touser, source = cls._get_config(db)
        if not api_url:
            logger.warning(f"小秘书推送接口未配置，无法向工号 {emp_no} 发送验证码")
            return False, "系统尚未配置小秘书消息推送接口，请联系系统管理员维护"

        # 使用 secrets 安全生成 6 位数字验证码
        code = f"{secrets.randbelow(900000) + 100000}"

        # 确定收件人 touser：
        # 生产安全规范：默认严格投递给当前员工工号 emp_no，防止敏感验证码错发给固定账号
        # 仅当系统显式开启测试模式（settings.XIAOMISHU_TEST_MODE 为 True）且配置了测试人时，才允许转发至固定账号
        if settings.XIAOMISHU_TEST_MODE and default_touser:
            touser = default_touser
        else:
            touser = emp_no
        beijing_time = now_utc.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        now_str = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
        greeting = f"{employee_name} 同事" if employee_name else f"工号 {emp_no}"
        content = [
            f"时间: {now_str}",
            f"来源: {source}",
            f"【One 大模型服务平台】{greeting}您好，您的登录验证码为: {code}，5 分钟内有效。如非本人操作请忽略此提醒。"
        ]

        payload = {
            "touser": touser,
            "content": "\n".join(content)
        }

        logger.info(f"正在向小秘书网关请求验证码推送: touser={touser}")

        # 调用推送接口，严格检查响应状态
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(api_url, json=payload)
                if resp.status_code != 200:
                    logger.error(f"小秘书推送接口返回非 200 HTTP 状态: {resp.status_code}")
                    return False, f"小秘书服务响应异常 (HTTP {resp.status_code})，请稍后重试"

                content_type = resp.headers.get("content-type", "")
                res_data = resp.json() if "application/json" in content_type else {}
                if isinstance(res_data, dict):
                    if res_data.get("errcode") and res_data.get("errcode") != 0:
                        logger.error(f"小秘书推送业务错误: errcode={res_data.get('errcode')}")
                        return False, f"小秘书推送失败: {res_data.get('errmsg') or '业务接口拒绝'}"
                    if res_data.get("success") is False:
                        logger.error("小秘书推送业务 success 字段为 False")
                        return False, f"小秘书推送失败: {res_data.get('message') or '业务执行失败'}"

        except Exception as e:
            logger.error(f"调用小秘书推送服务网络异常: {str(e)}")
            return False, "连接小秘书推送服务失败，请检查网络或稍后重试"

        # 推送服务确认成功后，将安全哈希及过期时间落库
        code_hash = cls._hash_code(emp_no, code)
        expire_at = now_utc + timedelta(minutes=5)
        new_record = VerificationCode(
            emp_no=emp_no,
            code_hash=code_hash,
            expire_at=expire_at,
            sent_at=now_utc,
            is_used=False
        )
        db.add(new_record)
        db.commit()

        logger.info(f"验证码推送成功且已落库: emp_no={emp_no}")
        return True, "验证码已成功推送至您的小秘书客户端，请查收"

    @classmethod
    def verify_code(
        cls,
        db: Session,
        emp_no: str,
        input_code: str,
        client_ip: str = "127.0.0.1"
    ) -> Tuple[bool, str]:
        """
        校验验证码：
        - 校验连续输错锁定
        - 比对安全哈希
        - 校验成功后原子消费，防止并发重复登录
        """
        emp_no = emp_no.strip()
        input_code = input_code.strip()

        # 检查是否处于输错锁定状态
        AuthService._check_and_raise_lockout(db, "emp_no", emp_no)
        AuthService._check_and_raise_lockout(db, "ip", client_ip)

        now_utc = datetime.utcnow()

        # 查找最新一条未被消费且未过期的验证码
        record = db.query(VerificationCode).filter(
            VerificationCode.emp_no == emp_no,
            VerificationCode.is_used.is_(False),
            VerificationCode.expire_at > now_utc
        ).order_by(VerificationCode.id.desc()).first()

        if not record:
            f_count = AuthService._record_failure(db, "emp_no", emp_no)
            AuthService._record_failure(db, "ip", client_ip)
            remain = max(0, settings.AUTH_MAX_FAILURES - f_count)
            return False, f"尚未获取有效验证码或验证码已过期，请重新获取（剩余尝试次数：{remain}）"

        # 安全比对哈希
        expected_hash = cls._hash_code(emp_no, input_code)
        if record.code_hash != expected_hash:
            f_count = AuthService._record_failure(db, "emp_no", emp_no)
            AuthService._record_failure(db, "ip", client_ip)
            remain = max(0, settings.AUTH_MAX_FAILURES - f_count)
            if remain == 0:
                return False, f"验证码连续输错达上限，账号已被临时锁定 {settings.AUTH_LOCKOUT_MINUTES} 分钟"
            return False, f"验证码错误，请核对后重试（剩余尝试次数：{remain}）"

        # 原子消费：通过条件更新确保并发下仅有一个请求能够成功将 is_used 置为 True
        affected = db.query(VerificationCode).filter(
            VerificationCode.id == record.id,
            VerificationCode.is_used.is_(False)
        ).update({"is_used": True})

        if affected != 1:
            db.rollback()
            return False, "验证码已被使用，请重新获取"

        # 验证通过，清理失败锁定记录
        AuthService._clear_failure(db, "emp_no", emp_no)
        AuthService._clear_failure(db, "ip", client_ip)
        db.commit()

        return True, "验证成功"
