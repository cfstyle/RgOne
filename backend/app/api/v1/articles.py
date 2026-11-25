from __future__ import annotations
import json
import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.api.deps import get_current_admin
from backend.app.models.article import Article
from backend.app.models.admin_user import AdminUser

router = APIRouter(tags=["案例广场与实践文章"])

ALLOWED_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


class ArticleCreateUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    summary: Optional[str] = Field(None, max_length=512)
    category: str = Field("入门指南", max_length=64)
    tags: Optional[List[str]] = None
    content_md: str
    author_name: str = "AI 赋能工作组"
    is_pinned: bool = False
    is_published: bool = True


@router.get("/articles", summary="公开文章列表")
def list_articles(
    category: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db)
):
    query = db.query(Article).filter(Article.is_published.is_(True))
    if category:
        query = query.filter(Article.category == category)
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.filter((Article.title.ilike(kw)) | (Article.summary.ilike(kw)))

    total = query.count()
    records = query.order_by(Article.is_pinned.desc(), Article.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for a in records:
        try:
            tags_list = json.loads(a.tags) if a.tags else []
        except Exception:
            tags_list = []

        items.append({
            "id": a.id,
            "title": a.title,
            "summary": a.summary,
            "category": a.category,
            "tags": tags_list,
            "author_name": a.author_name,
            "view_count": a.view_count,
            "is_pinned": a.is_pinned,
            "created_at": a.created_at.strftime("%Y-%m-%d"),
        })

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.get("/articles/{article_id}", summary="文章正文详情")
def get_article_detail(article_id: int, db: Session = Depends(get_db)):
    a = db.query(Article).filter(Article.id == article_id, Article.is_published.is_(True)).first()
    if not a:
        raise HTTPException(status_code=404, detail="文章不存在或已下线")

    # 递增阅读量
    a.view_count += 1
    db.commit()

    try:
        tags_list = json.loads(a.tags) if a.tags else []
    except Exception:
        tags_list = []

    return {
        "success": True,
        "data": {
            "id": a.id,
            "title": a.title,
            "summary": a.summary,
            "category": a.category,
            "tags": tags_list,
            "content_md": a.content_md,
            "author_name": a.author_name,
            "view_count": a.view_count,
            "is_pinned": a.is_pinned,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M"),
        }
    }


# ---------------------- 管理员文章管理接口 ----------------------

@router.get("/admin/articles", summary="管理员获取所有文章 (含草稿)")
def admin_list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Article)
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.filter((Article.title.ilike(kw)) | (Article.category.ilike(kw)))

    total = query.count()
    records = query.order_by(Article.is_pinned.desc(), Article.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for a in records:
        items.append({
            "id": a.id,
            "title": a.title,
            "category": a.category,
            "author_name": a.author_name,
            "view_count": a.view_count,
            "is_pinned": a.is_pinned,
            "is_published": a.is_published,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    return {"success": True, "total": total, "items": items}


@router.post("/admin/articles", summary="管理员发布/创建文章")
def admin_create_article(
    data: ArticleCreateUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    new_art = Article(
        title=data.title.strip(),
        summary=data.summary.strip() if data.summary else None,
        category=data.category.strip(),
        tags=json.dumps(data.tags or [], ensure_ascii=False),
        content_md=data.content_md,
        author_name=data.author_name.strip() if data.author_name else "AI 赋能工作组",
        is_pinned=data.is_pinned,
        is_published=data.is_published,
    )
    db.add(new_art)
    db.commit()
    db.refresh(new_art)
    return {"success": True, "message": "文章已保存", "id": new_art.id}


@router.put("/admin/articles/{article_id}", summary="管理员更新文章")
def admin_update_article(
    article_id: int,
    data: ArticleCreateUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    art = db.query(Article).filter(Article.id == article_id).first()
    if not art:
        raise HTTPException(status_code=404, detail="文章未找到")

    art.title = data.title.strip()
    art.summary = data.summary.strip() if data.summary else None
    art.category = data.category.strip()
    art.tags = json.dumps(data.tags or [], ensure_ascii=False)
    art.content_md = data.content_md
    art.author_name = data.author_name.strip()
    art.is_pinned = data.is_pinned
    art.is_published = data.is_published

    db.commit()
    return {"success": True, "message": "文章已更新"}


@router.delete("/admin/articles/{article_id}", summary="管理员删除文章")
def admin_delete_article(
    article_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    art = db.query(Article).filter(Article.id == article_id).first()
    if not art:
        raise HTTPException(status_code=404, detail="文章未找到")

    db.delete(art)
    db.commit()
    return {"success": True, "message": "文章已删除"}


@router.post("/admin/articles/upload-image", summary="上传案例文章配图 (本地持久化托管)")
async def upload_article_image(
    file: UploadFile = File(...),
    admin: AdminUser = Depends(get_current_admin)
):
    """
    保存本地图片至 data/storage/images/
    返回供 Markdown 调用的相对路径 /api/v1/static/images/{filename}
    """
    orig_name = file.filename or "image.png"
    ext = os.path.splitext(orig_name)[1].lower()

    if ext not in ALLOWED_IMG_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"仅支持图片格式: {', '.join(sorted(ALLOWED_IMG_EXTS))}"
        )

    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = settings.resolved_images_dir / stored_name

    content = await file.read()
    with open(dest_path, "wb") as f_out:
        f_out.write(content)

    image_url = f"/api/v1/static/images/{stored_name}"
    return {
        "success": True,
        "message": "图片上传成功",
        "url": image_url,
        "original_filename": orig_name
    }
