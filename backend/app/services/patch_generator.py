from __future__ import annotations
import re
import yaml
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.models.setting import SystemSetting
from backend.app.services.new_api_client import new_api_client


class PatchGenerator:
    """动态生成 DeepSeek Harness 客户端专用配置补丁 cordis.patch.yml"""

    @classmethod
    async def generate_cordis_patch_yaml(cls, db: Session, api_key: Optional[str] = None) -> str:
        """
        实时读取当前网关配置与可用模型列表，构造标准 cordis.patch.yml 格式
        """
        # 读取配置项
        s_url = db.query(SystemSetting).filter(SystemSetting.key == "new_api_base_url").first()
        base_url = (s_url.value if s_url and s_url.value else settings.NEW_API_BASE_URL).rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        s_pid = db.query(SystemSetting).filter(SystemSetting.key == "default_provider_id").first()
        provider_id = (s_pid.value if s_pid and s_pid.value else settings.DEFAULT_PROVIDER_ID).strip()

        s_pname = db.query(SystemSetting).filter(SystemSetting.key == "default_provider_name").first()
        provider_name = (s_pname.value if s_pname and s_pname.value else settings.DEFAULT_PROVIDER_NAME).strip()

        s_model = db.query(SystemSetting).filter(SystemSetting.key == "default_agent_model").first()
        default_model = (s_model.value if s_model and s_model.value else settings.DEFAULT_AGENT_MODEL).strip()

        # 生成环境变量名，如 new-api-1 -> NEW_API_1_API_KEY
        clean_env_name = re.sub(r"[^A-Za-z0-9]", "_", provider_id).upper()
        api_key_env = f"{clean_env_name}_API_KEY"

        # 获取可用模型列表
        models_data = await new_api_client.list_models()
        formatted_models: List[Dict[str, Any]] = []

        for m in models_data:
            mid = m.get("id", "")
            inputs = m.get("input", ["text"])
            formatted_models.append({
                "id": mid,
                "name": mid,
                "input": inputs,
            })

        patch_structure = [
            {
                "id": "session-log-deepseek",
                "name": "@deepseek-ai/dsh-session-log-deepseek",
                "config": {"enabled": False},
            },
            {
                "id": "llm-pi-ai",
                "name": "@deepseek-ai/dsh-llm-pi-ai",
                "config": {
                    "providers": {
                        provider_id: {
                            "displayName": provider_name,
                            "apiKeyEnv": api_key_env,
                            "api": "openai-completions",
                            "baseURL": base_url,
                            "models": formatted_models,
                        }
                    }
                },
            },
            {
                "id": "ui-chat",
                "name": "@deepseek-ai/dsh-client-ui-chat",
                "config": {"transcriptView": "standard", "performanceUsage": "detailed"},
            },
            {
                "id": "ui-settings",
                "name": "@deepseek-ai/dsh-client-ui-settings",
                "config": {"enabled": True},
            },
        ]
        model_ids = [model["id"] for model in formatted_models]
        if model_ids:
            patch_structure.append({
                "id": "agent-default-model",
                "name": "@deepseek-ai/dsh-agent-default-model",
                "config": {
                    "provider": provider_id,
                    "model": default_model if default_model in model_ids else model_ids[0],
                },
            })

        # 序列化为规范 YAML
        yaml_content = yaml.safe_dump(
            patch_structure,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

        header_comment = (
            "# =====================================================================\n"
            "# DeepSeek Harness 内网配置补丁文件 (cordis.patch.yml)\n"
            "# 适用网关: 行内统一大模型平台 (new-api)\n"
            "# 使用方式:\n"
            "# 1. 客户端右上角点击「打开配置文件」所在目录；\n"
            "# 2. 将本文件覆盖同名 cordis.patch.yml；\n"
            "# 3. 重启客户端并在「设置 -> 模型 -> 自定义模型 API」中填入专属 API Key。\n"
            "# =====================================================================\n\n"
        )

        return header_comment + yaml_content
