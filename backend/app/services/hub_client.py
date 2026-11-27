from __future__ import annotations
import logging
from typing import Optional, Tuple
import httpx
from backend.app.core.config import settings

logger = logging.getLogger("hub_client")


class CapabilityHubClient:
    """RgOne 与 AI Capability Hub 内部协同客户端"""

    @staticmethod
    def is_configured() -> bool:
        return bool((settings.CAPABILITY_HUB_BASE_URL or "").strip())

    @classmethod
    async def sync_employee_status(
        cls,
        emp_no: str,
        is_active: bool,
        reason: str = "",
    ) -> Tuple[bool, str]:
        """
        将员工停用/复职状态同步至 Capability Hub（吊销或恢复 Web JWT 与 ide-client MCP Token）。
        未配置 CAPABILITY_HUB_BASE_URL 时直接跳过返回 True。
        """
        base_url = (settings.CAPABILITY_HUB_BASE_URL or "").strip().rstrip("/")
        if not base_url:
            return True, "not_configured"

        secret = (settings.CAPABILITY_HUB_INTERNAL_SECRET or "").strip()
        if not secret:
            return False, "未配置 CAPABILITY_HUB_INTERNAL_SECRET"

        action = "restore" if is_active else "revoke"
        url = f"{base_url}/api/v1/internal/users/{emp_no.strip()}/{action}"
        headers = {"X-Internal-Secret": secret}
        payload = {"reason": reason or ("employee_restored" if is_active else "employee_disabled")}

        try:
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    return True, "synced"
                detail: Optional[str] = None
                try:
                    detail = resp.json().get("detail")
                except Exception:
                    detail = resp.text[:200]
                return False, f"HTTP {resp.status_code}: {detail or 'Hub 拒绝同步'}"
        except Exception as exc:
            logger.warning("同步员工 %s 状态至 Capability Hub 失败: %s", emp_no, exc)
            return False, str(exc)

    @classmethod
    async def issue_ide_token(
        cls,
        emp_no: str,
    ) -> Tuple[bool, Optional[str], Optional[str], str]:
        """向 Capability Hub 换取指定员工的 ide-client 长效 MCP Token（严格由 Hub 独立密钥签发）"""
        base_url = (settings.CAPABILITY_HUB_BASE_URL or "").strip().rstrip("/")
        if not base_url:
            return False, None, None, "not_configured"

        secret = (settings.CAPABILITY_HUB_INTERNAL_SECRET or "").strip()
        if not secret:
            return False, None, None, "未配置 CAPABILITY_HUB_INTERNAL_SECRET"

        url = f"{base_url}/api/v1/internal/users/{emp_no.strip()}/ide-token"
        headers = {"X-Internal-Secret": secret}

        try:
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                resp = await client.post(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return (
                        True,
                        data.get("token"),
                        data.get("gateway_url"),
                        "issued",
                    )
                detail: Optional[str] = None
                try:
                    detail = resp.json().get("detail")
                except Exception:
                    detail = resp.text[:200]
                return False, None, None, f"HTTP {resp.status_code}: {detail or 'Hub 拒绝签发'}"
        except Exception as exc:
            logger.warning("向 Capability Hub 换取员工 %s MCP Token 失败: %s", emp_no, exc)
            return False, None, None, str(exc)
