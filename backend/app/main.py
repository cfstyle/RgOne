from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.services.init_db import init_database
from backend.app.services.new_api_client import new_api_client
from backend.app.services.log_sync import LogSyncService
from backend.app.api.v1.api import api_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("rgone_portal")


async def _background_log_syncer():
    """后台定时增量同步消费日志任务 (每 5 分钟轮询一次，与前端手动刷新形成双轨兜底)"""
    logger.info("后台日志增量同步定时轮询任务已启动 (轮询周期: 300 秒)")
    while True:
        try:
            await asyncio.sleep(300)
            added = await LogSyncService.sync_incremental_logs()
            if added > 0:
                logger.info(f"后台自动定时增量同步完成，新增 {added} 条用量消费记录")
        except asyncio.CancelledError:
            logger.info("后台日志增量同步任务已安全终止")
            break
        except Exception as e:
            logger.warning(f"后台自动同步网关日志异常: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动前初始化
    logger.info("正在执行数据库检查与基础数据初始化...")
    init_database()
    
    # 尝试从持久化 DB 装载已保存的网关凭证与配置
    db = SessionLocal()
    try:
        new_api_client.load_from_db(db)
    finally:
        db.close()

    # 启动常驻后台轮询任务
    syncer_task = asyncio.create_task(_background_log_syncer())

    logger.info(f"RgOne 服务已启动，网关运行时通信模式: {'MOCK' if new_api_client.is_mock else 'REAL (内网网关直连)'}")
    yield
    # 关闭时清理
    logger.info("RgOne 服务正在安全关闭，注销后台定时任务...")
    syncer_task.cancel()
    try:
        await syncer_task
    except asyncio.CancelledError:
        pass
    logger.info("RgOne 服务已安全关闭")


app = FastAPI(
    title="行内大模型自助接入与案例门户 API",
    description="支持 DeepSeek Harness 零门槛接入向导、工号双向核验签发、细颗粒度用量分析与全套管理后台",
    version="1.0.0",
    lifespan=lifespan
)

# 允许跨域（本地开发及内网环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载业务路由
app.include_router(api_router, prefix="/api")

# 挂载本地持久化静态资源目录
downloads_dir = settings.resolved_downloads_dir
images_dir = settings.resolved_images_dir

app.mount("/api/v1/static/downloads", StaticFiles(directory=str(downloads_dir)), name="static_downloads")
app.mount("/api/v1/static/images", StaticFiles(directory=str(images_dir)), name="static_images")


@app.get("/health", tags=["系统监控"])
def health_check():
    """轻量级健康检查端点"""
    return {
        "status": "healthy",
        "app_env": settings.APP_ENV,
        "mock_new_api": new_api_client.is_mock,
    }


# 挂载生产模式前端构建产物（若存在 dist 目录）
dist_dir = (Path(__file__).resolve().parent.parent.parent / "frontend" / "dist").resolve()
if dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="frontend_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa_frontend(request: Request, full_path: str):
        # 排除 API 请求
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        target_file = dist_dir / full_path
        if target_file.is_file():
            return FileResponse(str(target_file))
        return FileResponse(str(dist_dir / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
