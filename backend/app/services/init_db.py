from __future__ import annotations
import hashlib
import json
import logging
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import engine, SessionLocal, Base
from backend.app.core.security import hash_password, encrypt_secret
from backend.app.models.admin_user import AdminUser
from backend.app.models.employee import Employee
from backend.app.models.setting import SystemSetting
from backend.app.models.article import Article
from backend.app.models.shared_file import SharedFile

logger = logging.getLogger("init_db")


def seed_demo_employees(db: Session):
    """
    仅在测试环境或显式演示模式下注入示范员工白名单。
    生产初始化绝对不自动写入示范账号，绝不覆盖已有员工的姓名或部门信息。
    """
    demo_employees = [
        ("06700956", "陈飞", "金融科技部 · 核心架构组", "0956"),
        ("06701099", "李晓华", "网络金融部 · 产品运营组", "1099"),
        ("06700888", "王大力", "风险管理部 · 智能风控组", "0888"),
        ("001024", "陈飞", "金融科技部 · 核心架构组", "1024"),
    ]
    for emp_no, name, dept, phone in demo_employees:
        emp = db.query(Employee).filter(Employee.emp_no == emp_no).first()
        if not emp:
            db.add(Employee(
                emp_no=emp_no,
                name=name,
                department=dept,
                phone_last4=phone,
                is_active=True
            ))
    db.commit()


def init_database():
    """初始化数据库表与基础种子数据（生产安全：仅建表、默认管理员与基础配置，不污染员工白名单）"""
    Base.metadata.create_all(bind=engine)
    # 平滑增量列迁移：兼容旧库补充 employees.hub_sync_status
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(employees)").fetchall()}
        if cols and "hub_sync_status" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE employees ADD COLUMN hub_sync_status VARCHAR(32) NOT NULL DEFAULT 'synced'"
            )
    db: Session = SessionLocal()
    try:
        # 1. 初始化默认管理员
        admin = db.query(AdminUser).filter(AdminUser.username == settings.INIT_ADMIN_USERNAME).first()
        if not admin:
            admin = AdminUser(
                username=settings.INIT_ADMIN_USERNAME,
                password_hash=hash_password(settings.INIT_ADMIN_PASSWORD),
                role="admin",
                is_active=True
            )
            db.add(admin)
            logger.info(f"已创建默认超级管理员: {settings.INIT_ADMIN_USERNAME}")

        # 2. 初始化核心系统设置
        default_settings = [
            ("new_api_base_url", settings.NEW_API_BASE_URL, "new-api 聚合网关 HTTP 地址"),
            ("new_api_access_token", encrypt_secret(settings.NEW_API_ACCESS_TOKEN or ""), "new-api 系统访问令牌 (加密存储)"),
            ("new_api_user_id", str(settings.NEW_API_USER_ID), "new-api 服务账号 User ID"),
            ("default_provider_id", settings.DEFAULT_PROVIDER_ID, "客户端 Provider ID 标识"),
            ("default_provider_name", settings.DEFAULT_PROVIDER_NAME, "客户端模型供应商显示名称"),
            ("default_agent_model", settings.DEFAULT_AGENT_MODEL, "客户端默认 Agent 编程/分析模型"),
            ("last_log_sync_ts", "0", "最后一次增量日志同步时间戳(秒)"),
        ]
        for key, val, desc in default_settings:
            existing = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not existing:
                db.add(SystemSetting(key=key, value=val, description=desc))

        # 3. 初始化示范案例文章（空库时初始化）
        first_article = db.query(Article).first()
        if not first_article:
            demo_article = Article(
                title="DeepSeek Harness 客户端金融代码辅助最佳实践",
                summary="介绍如何在 DeepSeek Harness 客户端中利用行内聚合网关高效进行代码重构、单元测试生成与 SQL 调优。",
                category="代码实践",
                tags=json.dumps(["DeepSeek", "代码辅助", "提效"], ensure_ascii=False),
                content_md="""# DeepSeek Harness 客户端内网高效使用指南

欢迎使用行内自建大模型门户！本指南帮助你在 3 分钟内完成环境搭建与实战上手。

## 一、为什么选用 DeepSeek Harness？

* **极致隐私与安全**：全内网离线运行，配置补丁已默认关闭遥测打点。
* **原生多模型支持**：接入行内 `new-api` 统一算力集群，可在编码、逻辑推演与多模态解析间秒级切换。
* **零配置漫游**：工号申领的 API Key 长期有效，更换工作机只需同步配置文件即可。

## 二、核心配置核对清单

| 配置项 | 推荐值 | 说明 |
| :--- | :--- | :--- |
| **Provider ID** | `new-api-1` | 保持与补丁一致 |
| **显示名称** | `行内大模型平台` | 界面标识 |
| **API 地址** | `http://30.20.4.144:3001/v1` | 内网网关端点 |
| **API 协议** | `OpenAI Chat Completions` | 标准兼容协议 |

## 三、代码示例：SQL 批量调优 Prompt

```sql
-- 原始慢 SQL
SELECT u.name, o.order_id, o.amount
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE o.created_at >= '2026-01-01'
ORDER BY o.amount DESC
LIMIT 100;
```

**提示词推荐：**
> "请作为资深数据库性能专家，分析上述 SQL 在大表关联下的执行计划瓶颈，并给出包含覆盖索引设计与下推过滤的优化重写方案。"
""",
                author_name="行内 AI 赋能工作组",
                view_count=128,
                is_pinned=True,
                is_published=True
            )
            db.add(demo_article)

        # 4. 精确识别并清理历史 43 字节占位安装包推荐标记（严格限定 category == 'installer'，绝不误伤普通推荐资料）
        known_placeholder_shas = {
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            hashlib.sha256(b"MOCK_DEEPSEEK_HARNESS_INSTALLER_PLACEHOLDER").hexdigest(),
            hashlib.sha256(b"MOCK_DEEPSEEK_HARNESS_INSTALLER_PAYLOAD").hexdigest(),
        }
        small_installers = db.query(SharedFile).filter(
            SharedFile.category == "installer",
            SharedFile.file_size <= 128,
            SharedFile.is_recommended == True
        ).all()
        for sf in small_installers:
            # 严格依据 SHA-256 摘要或已知占位指纹判断
            if sf.sha256 in known_placeholder_shas:
                sf.is_recommended = False
            else:
                disk_path = settings.resolved_downloads_dir / sf.stored_filename
                if disk_path.exists():
                    try:
                        content_sample = disk_path.read_bytes()[:64]
                        if b"MOCK_" in content_sample or b"PLACEHOLDER" in content_sample:
                            sf.is_recommended = False
                    except Exception:
                        pass

        db.commit()
        logger.info("数据库初始化与系统配置注入完毕（生产员工白名单保持纯净）")
    except Exception as e:
        db.rollback()
        logger.error(f"初始化数据库失败: {e}")
        raise
    finally:
        db.close()
