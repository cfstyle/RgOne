from __future__ import annotations
import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional
import httpx
from backend.app.core.config import settings

logger = logging.getLogger("new_api_client")


class TokenCreationRejected(RuntimeError):
    """网关明确拒绝签发；调用方可安全重试。"""


class NewApiClient:
    """
    new-api 聚合网关 HTTP 适配层
    支持真实网络请求与全功能 Mock 模式（用于无网关环境下的本地研发自测）
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        access_token: Optional[str] = None,
        user_id: Optional[int] = None,
        mock: Optional[bool] = None,
    ):
        self.base_url = (base_url or settings.NEW_API_BASE_URL).rstrip("/")
        self.access_token = (access_token if access_token is not None else settings.NEW_API_ACCESS_TOKEN or "").strip()
        self.user_id = user_id if user_id is not None else settings.NEW_API_USER_ID
        self._mock_override = mock

        # 内存缓存：模型列表缓存 (60秒过期)
        self._models_cache: Optional[List[Dict[str, Any]]] = None
        self._models_cache_time: float = 0

        # Mock 模式内部状态存储
        self._mock_tokens: Dict[int, Dict[str, Any]] = {}
        self._mock_next_token_id: int = 1000

    @property
    def is_mock(self) -> bool:
        if settings.app_mode == "production":
            return False
        if self._mock_override is not None:
            return self._mock_override
        return settings.app_mode == "test" or (
            settings.app_mode == "development" and settings.MOCK_NEW_API and not self.access_token
        )

    def load_from_db(self, db) -> None:
        """从系统配置表中读取已持久化的网关配置与加密令牌，实现开箱即用与重启自愈"""
        from backend.app.models.setting import SystemSetting
        from backend.app.core.security import decrypt_secret

        try:
            url_rec = db.query(SystemSetting).filter(SystemSetting.key == "new_api_base_url").first()
            if url_rec and url_rec.value:
                self.base_url = url_rec.value.rstrip("/")

            token_rec = db.query(SystemSetting).filter(SystemSetting.key == "new_api_access_token").first()
            if token_rec and token_rec.value:
                decrypted = decrypt_secret(token_rec.value)
                if decrypted:
                    self.access_token = decrypted.strip()
                    logger.info("已装载数据库中的 new-api Access Token")

            uid_rec = db.query(SystemSetting).filter(SystemSetting.key == "new_api_user_id").first()
            if uid_rec and uid_rec.value:
                try:
                    self.user_id = int(uid_rec.value)
                except ValueError:
                    pass
        except Exception as e:
            logger.warning(f"从数据库加载 new-api 运行时凭证失败: {e}")

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if self.user_id:
            headers["New-Api-User"] = str(self.user_id)
        return headers

    def _configuration_error(self) -> Optional[str]:
        if not self.base_url:
            return "未配置 new-api 网关地址，请在系统设置中录入"
        if not self.access_token:
            return "未配置 new-api Access Token，请在系统设置中录入"
        return None

    async def test_connection(self) -> Dict[str, Any]:
        """测试网关连通性与服务令牌凭证"""
        if self.is_mock:
            return {
                "success": True,
                "mock": True,
                "message": "Mock 网关连接成功 (模拟模式已启用)",
                "base_url": self.base_url,
                "user_id": self.user_id,
            }

        configuration_error = self._configuration_error()
        if configuration_error:
            return {
                "success": False,
                "mock": False,
                "message": configuration_error,
            }

        url = f"{self.base_url}/api/user/self"
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        return {
                            "success": True,
                            "mock": False,
                            "message": "new-api 网关连通性验证通过",
                            "user_info": data.get("data", {}),
                        }
                    return {
                        "success": False,
                        "mock": False,
                        "message": data.get("message", "返回业务错误"),
                    }
                elif resp.status_code in (401, 403):
                    return {
                        "success": False,
                        "mock": False,
                        "message": f"鉴权失败 (HTTP {resp.status_code})，请检查 Access Token 与 User ID",
                    }
                else:
                    return {
                        "success": False,
                        "mock": False,
                        "message": f"网关返回异常状态码: {resp.status_code}",
                    }
        except Exception as e:
            logger.warning(f"网关连通性测试异常: {e}")
            return {
                "success": False,
                "mock": False,
                "message": f"连接网关异常: {str(e)}",
            }

    async def list_models(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        拉取当前网关全量可用模型列表 (带 60s 内存缓存)
        标准响应项包含 id, name, modalities (text, image), context_window 等能力标注
        """
        now = time.time()
        if not force_refresh and self._models_cache and (now - self._models_cache_time < 60):
            return self._models_cache

        if self.is_mock:
            mock_models = [
                {
                    "id": "DeepSeek-V4-Flash-0731-INT8",
                    "object": "model",
                    "owned_by": "deepseek",
                    "display_name": "DeepSeek V4 Flash (低延迟快速推断)",
                    "input": ["text"],
                    "context_length": 65536,
                    "is_recommended": True,
                    "description": "行内自部署主力低延迟推理模型，适合日常问答、代码辅助与长文本总结",
                },
                {
                    "id": "Qwen3.8-27B-BF16",
                    "object": "model",
                    "owned_by": "qwen",
                    "display_name": "Qwen 3.8 27B 高精度旗舰",
                    "input": ["text"],
                    "context_length": 32768,
                    "is_recommended": True,
                    "description": "通用综合能力优秀，具备极高的金融与中文语义理解水平",
                },
                {
                    "id": "Qwen3.7-Plus-VL-Thinking-INT8",
                    "object": "model",
                    "owned_by": "qwen",
                    "display_name": "Qwen 3.7+ VL 视觉多模态 (带思考链)",
                    "input": ["text", "image"],
                    "context_length": 32768,
                    "is_recommended": False,
                    "description": "支持票据、报表截图解析与多图混合推理，支持 Visual Thinking",
                },
                {
                    "id": "DeepSeek-R1-Distill-Qwen-32B",
                    "object": "model",
                    "owned_by": "deepseek",
                    "display_name": "DeepSeek R1 深度推理蒸馏版",
                    "input": ["text"],
                    "context_length": 65536,
                    "is_recommended": False,
                    "description": "擅长复杂数学计算、逻辑推演与深度代码生成",
                },
            ]
            self._models_cache = mock_models
            self._models_cache_time = now
            return mock_models

        url = f"{self.base_url}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    raw_data = resp.json().get("data", [])
                    processed = []
                    for m in raw_data:
                        mid = m.get("id", "")
                        # 智能多模态识别：若模型名含 VL / Vision / Multi，标注包含 image
                        is_vl = any(k in mid.upper() for k in ("VL", "VISION", "MULTIMODAL", "IMAGE", "4O"))
                        processed.append({
                            "id": mid,
                            "object": "model",
                            "owned_by": m.get("owned_by", "new-api"),
                            "display_name": mid,
                            "input": ["text", "image"] if is_vl else ["text"],
                            "context_length": 32768,
                            "is_recommended": "DEEPSEEK" in mid.upper() or "QWEN" in mid.upper(),
                            "description": "行内大模型网关提供",
                        })
                    self._models_cache = processed
                    self._models_cache_time = now
                    return processed
        except Exception as e:
            logger.warning(f"拉取模型列表失败: {e}")
            if self._models_cache:
                return self._models_cache

        return []

    async def create_token(self, name: str) -> Dict[str, Any]:
        """
        为员工创建专属 Token (无限额度、永不过期)
        妥善处理 new-api 创建时不直接回传 Key 的兼容性避坑逻辑
        """
        if self.is_mock:
            if getattr(self, "_mock_fail_create", False):
                raise TokenCreationRejected("网关创建 Token 失败: mock create failure")
            self._mock_next_token_id += 1
            tid = self._mock_next_token_id
            mock_key = f"sk-rgone-mock-{random.randint(10000000, 99999999)}{random.randint(10000000, 99999999)}"
            self._mock_tokens[tid] = {
                "id": tid,
                "name": name,
                "key": mock_key,
                "status": 1,
            }
            return {
                "id": tid,
                "name": name,
                "key": mock_key,
            }

        url = f"{self.base_url}/api/token/"
        payload = {
            "name": name,
            "expired_time": -1,
            "unlimited_quota": True,
            "remain_quota": 0,
            "model_limits_enabled": False,
            "group": "",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=self._headers())
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
                raise TokenCreationRejected("连接网关失败，Token 签发请求尚未发送") from None
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"new-api 创建 Token 结果未知: HTTP {resp.status_code}")
            
            res_json = resp.json()
            if res_json.get("success") is False:
                raise TokenCreationRejected("new-api 创建 Token 返回业务失败")

        # 创建接口可能不回传 Key。查不到时签发结果仍未知。
        token = await self.get_token_by_name(name, clean_duplicates=False)
        if token is None:
            raise RuntimeError("暂时无法检索到刚刚创建的 Token")
        return token

    async def get_token_by_name(self, name: str, *, clean_duplicates: bool = True) -> Optional[Dict[str, Any]]:
        """
        按名称精准检索网关已存在的有效 Token（用于崩溃恢复核对）：
        - 若发现网关存在多个同名残留 Token，自动清理历史冗余，确保网关有效 Key 唯一
        - 获取有效明文 Key 凭据，若网关回传掩码自动调用二次换取
        """
        if self.is_mock:
            matches = [t for t in self._mock_tokens.values() if t.get("name") == name]
            if not matches:
                return None
            if len(matches) > 1:
                if not clean_duplicates:
                    raise RuntimeError("网关存在多个同名 Token，无法确认唯一结果")
                matches.sort(key=lambda x: x["id"], reverse=True)
                for extra in matches[1:]:
                    if not await self.delete_token(extra["id"]):
                        raise RuntimeError("无法确认同名 Token 已删除")
            target = matches[0]
            return {
                "id": target["id"],
                "name": target["name"],
                "key": target.get("key", ""),
            }

        url = f"{self.base_url}/api/token/search"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params={"keyword": name}, headers=self._headers())
            if resp.status_code != 200:
                raise RuntimeError(f"网关按名称检索 Token 失败: HTTP {resp.status_code}")
            body = resp.json()
            if body.get("success") is not True:
                raise RuntimeError("网关未返回可确认的 Token 查询结果")
            raw_data = body.get("data")
            if isinstance(raw_data, list):
                data = raw_data
            elif isinstance(raw_data, dict) and "items" in raw_data:
                items = raw_data.get("items")
                if items is None:
                    data = []
                elif isinstance(items, list):
                    data = items
                else:
                    raise RuntimeError("网关未返回可确认的 Token 查询结果")
            else:
                raise RuntimeError("网关未返回可确认的 Token 查询结果")
            matching = [item for item in data if item.get("name") == name]
            if not matching:
                return None
            if len(matching) > 1 and not clean_duplicates:
                raise RuntimeError("网关存在多个同名 Token，无法确认唯一结果")
            if any(not item.get("id") for item in matching):
                raise RuntimeError("网关返回的同名 Token 缺少 ID")

            matching.sort(key=lambda item: item["id"], reverse=True)
            for extra in matching[1:]:
                if not await self.delete_token(extra["id"]):
                    raise RuntimeError("无法确认同名 Token 已删除")

            target = matching[0]
            token_id = target["id"]
            key_str = target.get("key") or ""
            if not key_str or "*" in key_str:
                key_url = f"{self.base_url}/api/token/{token_id}/key"
                k_resp = await client.post(key_url, headers=self._headers())
                if k_resp.status_code != 200:
                    raise RuntimeError(f"网关获取 Token 明文失败: HTTP {k_resp.status_code}")
                key_body = k_resp.json()
                if key_body.get("success") is not True:
                    raise RuntimeError("网关获取 Token 明文返回业务失败")
                k_data = key_body.get("data")
                if isinstance(k_data, str):
                    key_str = k_data
                elif isinstance(k_data, dict):
                    key_str = k_data.get("key") or ""

            if key_str and not key_str.startswith("sk-"):
                key_str = f"sk-{key_str}"

            return {"id": token_id, "name": name, "key": key_str}

    async def update_token_status(self, token_id: int, status: int) -> bool:
        """更新 Token 状态：1=启用, 2=禁用（严格校验 HTTP 状态与业务 success 字段）"""
        if self.is_mock:
            if getattr(self, "_mock_fail_status", False):
                raise RuntimeError("网关更新 Token 状态返回业务失败: mock failure")
            self._mock_tokens[token_id] = self._mock_tokens.get(token_id, {"id": token_id})
            self._mock_tokens[token_id]["status"] = status
            return True

        url = f"{self.base_url}/api/token/?status_only=true"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.put(url, json={"id": token_id, "status": status}, headers=self._headers())
            if resp.status_code != 200:
                raise RuntimeError(f"网关更新 Token 状态失败: HTTP {resp.status_code} {resp.text}")

            content_type = resp.headers.get("content-type", "")
            data = resp.json() if "application/json" in content_type else {}
            if not data.get("success", True):
                raise RuntimeError(f"网关更新 Token 状态返回业务失败: {data.get('message', '未知网关错误')}")
            return True

    async def delete_token(self, token_id: int) -> bool:
        """删除 Token（严格校验 HTTP 状态与业务 success 字段）"""
        if self.is_mock:
            if getattr(self, "_mock_fail_delete", False):
                raise RuntimeError("网关删除 Token 失败: mock delete failure")
            self._mock_tokens.pop(token_id, None)
            return True

        url = f"{self.base_url}/api/token/{token_id}"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.delete(url, headers=self._headers())
            if resp.status_code != 200:
                raise RuntimeError(f"网关删除 Token 失败: HTTP {resp.status_code}")

            if resp.json().get("success") is not True:
                raise RuntimeError("网关未确认 Token 删除成功")
            return True

    async def fetch_consumption_logs(
        self,
        start_timestamp: int,
        page: int = 1,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        拉取消费日志 (type=2)，严格区分正常空页、请求失败与响应结构异常
        """
        if self.is_mock:
            return self._generate_mock_logs(start_timestamp)
        configuration_error = self._configuration_error()
        if configuration_error:
            raise RuntimeError(configuration_error)

        url = f"{self.base_url}/api/log/self"
        params = {
            "p": page,
            "page_size": page_size,
            "type": 2,
            "start_timestamp": start_timestamp,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                if resp.status_code != 200:
                    raise RuntimeError(f"网关拉取日志失败: HTTP {resp.status_code} {resp.text}")

                content_type = resp.headers.get("content-type", "")
                if "application/json" not in content_type:
                    raise RuntimeError(f"网关返回非 JSON 数据格式: {content_type}")

                res_json = resp.json()
                if not isinstance(res_json, dict):
                    raise RuntimeError(f"网关响应格式异常: 期望字典对象，实际为 {type(res_json)}")

                if res_json.get("success") is False:
                    raise RuntimeError(f"网关拉取日志返回业务失败: {res_json.get('message', '未知错误')}")

                data_list = res_json.get("data")
                if isinstance(data_list, dict) and "items" in data_list:
                    items = data_list.get("items")
                    data_list = [] if items is None else items
                elif data_list is None:
                    # 某些版本直接返回 items
                    data_list = res_json.get("items", [])

                if not isinstance(data_list, list):
                    raise RuntimeError(f"网关返回的 data 字段不是列表: {type(data_list)}")

                return data_list
        except httpx.RequestError as e:
            logger.error(f"连接网关拉取日志网络异常 (page={page}): {e}")
            raise RuntimeError(f"连接网关拉取日志失败: {str(e)}") from e

    def _generate_mock_logs(self, start_timestamp: int) -> List[Dict[str, Any]]:
        """生成仿真消费日志数据"""
        now = int(time.time())
        if start_timestamp >= now - 60:
            return []

        models = [
            "DeepSeek-V4-Flash-0731-INT8",
            "Qwen3.8-27B-BF16",
            "Qwen3.7-Plus-VL-Thinking-INT8",
            "DeepSeek-R1-Distill-Qwen-32B"
        ]
        logs = []
        # 默认生成近期的仿真日志
        base_time = max(start_timestamp, now - 86400 * 3)
        sim_id_base = 50000 + int(base_time % 10000)

        for i in range(12):
            log_time = base_time + (i * 3600) + random.randint(10, 1800)
            if log_time > now:
                break
            prompt_toks = random.randint(120, 2200)
            comp_toks = random.randint(80, 1800)
            model = random.choice(models)
            logs.append({
                "id": sim_id_base + i,
                "type": 2,
                "token_name": "EMP_001024_陈飞",
                "model_name": model,
                "prompt_tokens": prompt_toks,
                "completion_tokens": comp_toks,
                "quota": (prompt_toks + comp_toks) * 2,
                "use_time": random.randint(350, 4200),
                "is_stream": True,
                "created_at": log_time,
            })
        return logs


# 全局单例
new_api_client = NewApiClient()
