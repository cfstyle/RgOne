from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.shared_file import SharedFile
from backend.app.services.new_api_client import new_api_client
from backend.app.services.patch_generator import PatchGenerator
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/guide", tags=["接入向导与公共网关信息"])


@router.get("/models", summary="获取当前网关可用模型清单及能力标签")
async def get_available_models():
    """
    拉取当前接入内网网关的模型列表，包含推理类型、上下文长度、多模态支持（文本/图片）与推荐说明
    """
    models = await new_api_client.list_models()
    return {
        "success": True,
        "total": len(models),
        "data": models,
    }


@router.get("/status", summary="获取网关服务与连接健康状态")
async def get_gateway_status():
    """获取网关实时连通状态"""
    conn = await new_api_client.test_connection()
    return {
        "success": True,
        "gateway_connected": conn.get("success", False),
        "is_mock": conn.get("mock", False),
        "message": conn.get("message", ""),
    }


@router.get("/recommended-installer", summary="获取首页主推的客户端安装包信息")
def get_recommended_installer(db: Session = Depends(get_db)):
    """获取标记为 is_recommended=True 的最新真实安装包元数据（严格排除占位安装包）"""
    # 过滤掉 43 字节占位包
    valid_filter = (
        (SharedFile.category == "installer") &
        (SharedFile.file_size > 64) &
        (SharedFile.sha256 != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    )

    installer = db.query(SharedFile).filter(
        valid_filter,
        SharedFile.is_recommended.is_(True)
    ).order_by(SharedFile.id.desc()).first()

    if not installer:
        # 降级：取任意最新的真实安装包（非占位）
        installer = db.query(SharedFile).filter(
            valid_filter
        ).order_by(SharedFile.id.desc()).first()

    if not installer:
        return {"has_installer": False, "data": None}

    return {
        "has_installer": True,
        "data": {
            "id": installer.id,
            "title": installer.title,
            "version": installer.version,
            "description": installer.description,
            "original_filename": installer.original_filename,
            "file_size": installer.file_size,
            "sha256": installer.sha256,
            "download_count": installer.download_count,
            "download_url": f"/api/v1/files/download/{installer.id}",
        }
    }


@router.get("/cordis-patch-yml", summary="下载动态生成的 cordis.patch.yml 客户端补丁文件")
async def download_cordis_patch(db: Session = Depends(get_db)):
    """
    根据当前网关所有在线模型与配置，动态渲染包含遥测关闭、模型映射与 Agent 默认值的补丁文件
    """
    yaml_text = await PatchGenerator.generate_cordis_patch_yaml(db)
    return PlainTextResponse(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": 'attachment; filename="cordis.patch.yml"'
        }
    )

