from __future__ import annotations
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Generator
import pytest

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.app.core.config import settings
from backend.app.core.database import Base, get_db
import backend.app.core.database as core_db
import backend.app.services.init_db as init_db_mod
import backend.app.services.log_sync as log_sync_mod
from backend.app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_setup():
    """
    会话级隔离环境：
    - 独立临时目录
    - 独立 SQLite 数据库文件（绝不写入现存 data/app.db）
    - 独立文件存储目录
    """
    tmpdir = tempfile.mkdtemp(prefix="rgone_isolated_test_")
    db_path = Path(tmpdir) / "test.db"
    storage_downloads = Path(tmpdir) / "downloads"
    storage_images = Path(tmpdir) / "images"
    storage_downloads.mkdir(parents=True, exist_ok=True)
    storage_images.mkdir(parents=True, exist_ok=True)

    # 隔离配置
    settings.DATABASE_URL = f"sqlite:///{db_path}"
    settings.STORAGE_DOWNLOADS_DIR = str(storage_downloads)
    settings.STORAGE_IMAGES_DIR = str(storage_images)
    settings.MOCK_NEW_API = True
    settings.XIAOMISHU_API = "http://mock-xiaomishu.internal/send"
    settings.XIAOMISHU_SEND_USER = "test_user"

    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine, future=True)

    # 动态修补全局模块引用
    core_db.engine = test_engine
    core_db.SessionLocal = TestSessionLocal
    init_db_mod.engine = test_engine
    init_db_mod.SessionLocal = TestSessionLocal
    log_sync_mod.SessionLocal = TestSessionLocal

    def override_get_db() -> Generator[Session, None, None]:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # 初始化测试库表结构与核心系统配置
    init_db_mod.init_database()
    # 测试环境显式注入测试员工白名单（生产环境 init_database 绝不注入示范账号）
    seed_session = TestSessionLocal()
    try:
        init_db_mod.seed_demo_employees(seed_session)
    finally:
        seed_session.close()

    yield {
        "tmpdir": tmpdir,
        "db_path": db_path,
        "engine": test_engine,
        "SessionLocal": TestSessionLocal,
    }

    # 测试结束清理
    app.dependency_overrides.clear()
    test_engine.dispose()
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def db_session(test_setup) -> Generator[Session, None, None]:
    """单测试用例可直接使用的独立 DB 会话"""
    session = test_setup["SessionLocal"]()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_setup) -> TestClient:
    """挂载了独立数据库与依赖覆盖的测试客户端"""
    return TestClient(app)
