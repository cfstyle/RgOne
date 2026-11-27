from __future__ import annotations
import base64
import hashlib
import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote
import httpx
from backend.app.core.config import settings

logger = logging.getLogger("verdaccio_publisher")


class VerdaccioPublisher:
    """纯 Python httpx 实现的离线 Verdaccio npm Registry 推包器"""

    @staticmethod
    def _build_auth_headers() -> Dict[str, str]:
        token = (settings.VERDACCIO_AUTH_TOKEN or "").strip()
        if token:
            return {"Authorization": f"Bearer {token}"}

        username = (settings.VERDACCIO_AUTH_USERNAME or "").strip()
        password = (settings.VERDACCIO_AUTH_PASSWORD or "").strip()
        if username and password:
            raw = f"{username}:{password}".encode("utf-8")
            b64 = base64.b64encode(raw).decode("ascii")
            return {"Authorization": f"Basic {b64}"}

        return {}

    @classmethod
    async def publish_tarball(
        cls,
        *,
        package_name: str,
        version: str,
        tarball_bytes: bytes,
        package_json: Dict[str, Any],
        public_registry_url: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        向 Verdaccio PUT /{encoded_pkg} 推送 npm tarball：
        - 构造标准 npm publish payload（_attachments + base64 + dist.shasum + dist.integrity）
        - 未配置 VERDACCIO_URL 时返回优雅降级标记，不阻断本地/单元测试闭环
        """
        registry_base = (settings.VERDACCIO_URL or "").strip().rstrip("/")
        if not registry_base:
            return True, "verdaccio_not_configured"

        unscoped = package_name.split("/")[-1]
        attachment_name = f"{unscoped}-{version}.tgz"
        external_base = (public_registry_url or registry_base).rstrip("/")
        tarball_url = f"{external_base}/{package_name}/-/{attachment_name}"

        shasum = hashlib.sha1(tarball_bytes).hexdigest()
        sha512_b64 = base64.b64encode(hashlib.sha512(tarball_bytes).digest()).decode("ascii")
        tarball_b64 = base64.b64encode(tarball_bytes).decode("ascii")

        version_meta = dict(package_json)
        version_meta["_id"] = f"{package_name}@{version}"
        version_meta["name"] = package_name
        version_meta["version"] = version
        version_meta["dist"] = {
            "shasum": shasum,
            "integrity": f"sha512-{sha512_b64}",
            "tarball": tarball_url,
        }

        payload = {
            "_id": package_name,
            "name": package_name,
            "description": str(package_json.get("description") or ""),
            "dist-tags": {"latest": version},
            "versions": {version: version_meta},
            "access": "public",
            "_attachments": {
                attachment_name: {
                    "content_type": "application/octet-stream",
                    "data": tarball_b64,
                    "length": len(tarball_bytes),
                }
            },
        }

        encoded_pkg = quote(package_name, safe="")
        put_url = f"{registry_base}/{encoded_pkg}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **cls._build_auth_headers(),
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
                resp = await client.put(put_url, json=payload, headers=headers)
                if 200 <= resp.status_code < 300:
                    logger.info("已推送插件包至 Verdaccio: %s@%s", package_name, version)
                    return True, "published"
                detail = resp.text[:300]
                try:
                    j = resp.json()
                    detail = str(j.get("error") or j.get("reason") or detail)
                except Exception:
                    pass
                logger.error("Verdaccio 推包失败 (%s): %s", resp.status_code, detail)
                return False, f"Verdaccio 推包失败 (HTTP {resp.status_code}): {detail}"
        except Exception as exc:
            logger.warning("连接 Verdaccio 失败: %s", exc)
            return False, f"无法连接 Verdaccio ({registry_base}): {exc}"
