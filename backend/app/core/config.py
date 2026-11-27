from __future__ import annotations
import base64
import hashlib
import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录路径定位 (c:\...\RgOne)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "bW9ja19zZWNyZXRfa2V5X2Zvcl9kZXZlbG9wbWVudF8zMndpdGhfMDA="
    JWT_SECRET: str = "super_secret_jwt_key_for_rgone_portal_2026"
    JWT_ISSUER: str = "rgone"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    ADMIN_JWT_EXPIRE_HOURS: int = 24

    # AI Capability Hub 联动配置（同源整合 & 停用吊销同步）
    CAPABILITY_HUB_BASE_URL: str = ""
    CAPABILITY_HUB_INTERNAL_SECRET: str = ""

    # 统一对外入口与离线 Verdaccio 插件市场配置
    RGONE_PUBLIC_URL: str = ""
    VERDACCIO_URL: str = "http://verdaccio:4873"
    VERDACCIO_AUTH_TOKEN: str = ""
    VERDACCIO_AUTH_USERNAME: str = ""
    VERDACCIO_AUTH_PASSWORD: str = ""
    PLUGIN_REVIEWER_EMP_NOS: str = ""

    # 数据库连接
    DATABASE_URL: str = "sqlite:///./data/app.db"
    DEPLOYMENT_DATA_DIR: Optional[Path] = None

    # 初始化管理员
    INIT_ADMIN_USERNAME: str = "admin"
    INIT_ADMIN_PASSWORD: str = "Admin@RgOne2026"

    # new-api 网关配置
    NEW_API_BASE_URL: str = "http://30.20.4.144:3001"
    NEW_API_ACCESS_TOKEN: Optional[str] = ""
    NEW_API_USER_ID: int = 1
    MOCK_NEW_API: bool = True

    # 客户端默认配置
    DEFAULT_PROVIDER_ID: str = "new-api-1"
    DEFAULT_PROVIDER_NAME: str = "行内大模型平台"
    DEFAULT_AGENT_MODEL: str = "DeepSeek-V4-Flash-0731-INT8"

    # 存储目录
    STORAGE_DOWNLOADS_DIR: str = "./data/storage/downloads"
    STORAGE_IMAGES_DIR: str = "./data/storage/images"
    STORAGE_PLUGINS_DIR: str = "./data/storage/plugins"

    # 小秘书通知推送接口配置
    XIAOMISHU_API: Optional[str] = ""
    XIAOMISHU_SEND_USER: Optional[str] = ""
    XIAOMISHU_SOURCE: str = "金融市场部RPA"
    XIAOMISHU_TEST_MODE: bool = False  # 生产严格投递给员工本人；仅在测试模式显式启用时才转发至固定账号
    MOCK_XIAOMISHU_OTP: bool = False  # 仅限非生产环境本地开发联调模拟验证码，生产环境强制忽略
    MOCK_XIAOMISHU_CODE: str = "123456"

    # 频率控制（连续输错锁定）
    AUTH_MAX_FAILURES: int = 5
    AUTH_LOCKOUT_MINUTES: int = 10

    @property
    def fernet_key(self) -> bytes:
        """
        保证返回合法的 32 字节 url-safe base64 Fernet 密钥。
        若传入任意自定义字符串，通过 sha256 派生并安全编码。
        """
        raw = self.APP_SECRET_KEY.strip().encode("utf-8")
        try:
            # 校验是否本身就是合法的 32-byte urlsafe base64 key
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) == 32:
                return raw
        except Exception:
            pass
        # 否则使用 sha256 派生固定 32 字节并 base64 编码
        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)

    @property
    def app_mode(self) -> str:
        return self.APP_ENV.strip().lower()

    @property
    def deployment_data_dir(self) -> Optional[Path]:
        if self.DEPLOYMENT_DATA_DIR is None:
            return None
        return self.DEPLOYMENT_DATA_DIR / "test" if self.app_mode == "test" else self.DEPLOYMENT_DATA_DIR

    @property
    def resolved_database_url(self) -> str:
        data_dir = self.deployment_data_dir
        if data_dir is not None:
            data_dir.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{(data_dir / 'app.db').as_posix()}"
        if self.DATABASE_URL.startswith("sqlite:///./"):
            rel_path = self.DATABASE_URL.replace("sqlite:///./", "")
            abs_path = (BASE_DIR / rel_path).resolve()
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{abs_path}"
        return self.DATABASE_URL

    @property
    def resolved_downloads_dir(self) -> Path:
        data_dir = self.deployment_data_dir
        p = data_dir / "storage" / "downloads" if data_dir is not None else Path(self.STORAGE_DOWNLOADS_DIR)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def resolved_images_dir(self) -> Path:
        data_dir = self.deployment_data_dir
        p = data_dir / "storage" / "images" if data_dir is not None else Path(self.STORAGE_IMAGES_DIR)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def resolved_plugins_dir(self) -> Path:
        data_dir = self.deployment_data_dir
        p = data_dir / "storage" / "plugins" if data_dir is not None else Path(self.STORAGE_PLUGINS_DIR)
        if not p.is_absolute():
            p = (BASE_DIR / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def plugin_reviewer_list(self) -> List[str]:
        return [x.strip() for x in (self.PLUGIN_REVIEWER_EMP_NOS or "").split(",") if x.strip()]


settings = Settings()
