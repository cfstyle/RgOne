from __future__ import annotations
import hashlib
import os
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.api.deps import get_current_admin
from backend.app.models.shared_file import SharedFile
from backend.app.models.admin_user import AdminUser

router = APIRouter(tags=["资料与安装包下载中心"])

ALLOWED_EXTENSIONS = {
    ".exe", ".msi", ".zip", ".tar.gz", ".tgz", ".dmg", ".pkg",
    ".pdf", ".docx", ".xlsx", ".pptx", ".md", ".txt", ".json", ".yml", ".yaml"
}


class FileMetadataUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    is_recommended: Optional[bool] = None


@router.get("/files", summary="公开资料与安装包列表")
def list_shared_files(
    category: Optional[str] = Query(None, pattern="^(installer|manual|plugin|other)$"),
    db: Session = Depends(get_db)
):
    """公开下载中心列表，支持按分类检索"""
    query = db.query(SharedFile)
    if category:
        query = query.filter(SharedFile.category == category)

    files = query.order_by(SharedFile.is_recommended.desc(), SharedFile.id.desc()).all()
    items = []
    for f in files:
        items.append({
            "id": f.id,
            "category": f.category,
            "title": f.title,
            "version": f.version,
            "description": f.description,
            "original_filename": f.original_filename,
            "file_size": f.file_size,
            "sha256": f.sha256,
            "download_count": f.download_count,
            "is_recommended": f.is_recommended,
            "created_at": f.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "download_url": f"/api/v1/files/download/{f.id}",
        })
    return {
        "success": True,
        "data": items
    }


@router.get("/files/download/{file_id}", summary="流式下载指定资料或安装包")
def download_shared_file(file_id: int, db: Session = Depends(get_db)):
    """支持百兆级大文件流式断点续传下载，递增下载次数计数"""
    file_record = db.query(SharedFile).filter(SharedFile.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="资料文件不存在")

    target_path = settings.resolved_downloads_dir / file_record.stored_filename
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="磁盘上的文件已被移除")

    # 递增下载量
    file_record.download_count += 1
    db.commit()

    return FileResponse(
        path=str(target_path),
        filename=file_record.original_filename,
        media_type="application/octet-stream"
    )


# ---------------------- 管理员文件管理接口 ----------------------

@router.post("/admin/files/upload", summary="管理员分块流式上传资料/安装包")
async def upload_shared_file(
    file: UploadFile = File(...),
    category: str = Form("installer"),
    title: str = Form(...),
    version: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_recommended: bool = Form(False),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    分块流式接收上传文件（避免 500MB+ 安装包引发内存溢出）
    安全重命名防路径穿越，同时在流式写入过程中实时计算 SHA256 哈希
    """
    orig_name = file.filename or "unknown_file"
    ext = os.path.splitext(orig_name)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}，仅允许 {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 生成安全物理文件名
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = settings.resolved_downloads_dir / stored_name

    sha256_hasher = hashlib.sha256()
    total_size = 0

    chunk_size = 1024 * 1024  # 1MB 块
    try:
        with open(dest_path, "wb") as f_out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                f_out.write(chunk)
                sha256_hasher.update(chunk)
                total_size += len(chunk)
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件流式写入磁盘失败: {str(e)}"
        )

    # 若设为主推安装包，则先取消其它记录的主推标记
    if is_recommended and category == "installer":
        db.query(SharedFile).filter(SharedFile.category == "installer").update({"is_recommended": False})

    new_file = SharedFile(
        category=category,
        title=title.strip(),
        version=version.strip() if version else None,
        description=description.strip() if description else None,
        original_filename=orig_name,
        stored_filename=stored_name,
        file_size=total_size,
        sha256=sha256_hasher.hexdigest(),
        download_count=0,
        is_recommended=is_recommended,
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)

    return {
        "success": True,
        "message": "文件上传成功",
        "data": {
            "id": new_file.id,
            "title": new_file.title,
            "original_filename": new_file.original_filename,
            "file_size": new_file.file_size,
            "sha256": new_file.sha256,
        }
    }


@router.put("/admin/files/{file_id}", summary="修改资料元数据")
def update_shared_file(
    file_id: int,
    meta: FileMetadataUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """更新文件标题、分类、版本、描述或主推标记"""
    rec = db.query(SharedFile).filter(SharedFile.id == file_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="未找到目标文件记录")

    updates = meta.model_dump(exclude_unset=True)
    if updates.get("is_recommended") and rec.category == "installer":
        db.query(SharedFile).filter(SharedFile.category == "installer").update({"is_recommended": False})

    for k, v in updates.items():
        setattr(rec, k, v)

    db.commit()
    db.refresh(rec)
    return {"success": True, "message": "元数据已更新", "data": {"id": rec.id}}


@router.delete("/admin/files/{file_id}", summary="删除资料并同步清理磁盘文件")
def delete_shared_file(
    file_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """物理删除磁盘上的文件并移除数据库记录"""
    rec = db.query(SharedFile).filter(SharedFile.id == file_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="文件不存在")

    target_path = settings.resolved_downloads_dir / rec.stored_filename
    if target_path.exists():
        try:
            target_path.unlink()
        except Exception:
            pass

    db.delete(rec)
    db.commit()
    return {"success": True, "message": "文件及元数据已彻底删除"}
