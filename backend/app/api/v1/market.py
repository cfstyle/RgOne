from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.app.api.deps import get_current_admin, get_current_employee
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.admin_user import AdminUser
from backend.app.models.employee import Employee
from backend.app.models.plugin import Plugin, PluginVersion
from backend.app.services.plugin_validator import (
    PluginValidationError,
    validate_package_name,
    validate_plugin_tgz,
    validate_semver,
)
from backend.app.services.verdaccio_publisher import VerdaccioPublisher
from backend.app.services.xiaomishu_service import XiaomishuService

public_market_router = APIRouter(tags=["DSH 插件市场索引"])
portal_market_router = APIRouter(prefix="/market", tags=["门户插件市场"])
admin_plugins_router = APIRouter(prefix="/admin/plugins", tags=["管理员-插件市场治理"])


def _resolve_public_base(request: Request) -> str:
    if settings.RGONE_PUBLIC_URL and settings.RGONE_PUBLIC_URL.strip():
        return settings.RGONE_PUBLIC_URL.strip().rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
        or "127.0.0.1:8000"
    )
    return f"{proto}://{host}".rstrip("/")


def _parse_tags(raw: str) -> List[str]:
    try:
        parsed = json.loads(raw or "[]")
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass
    return []


def _parse_tags_input(raw: str) -> List[str]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return []
    if cleaned.startswith("["):
        return _parse_tags(cleaned)
    return [x.strip() for x in re.split(r"[,，\s]+", cleaned) if x.strip()]


def _serialize_version(pv: PluginVersion) -> Dict[str, Any]:
    try:
        pkg_snapshot = json.loads(pv.package_json_snapshot or "{}")
    except Exception:
        pkg_snapshot = {}
    return {
        "id": pv.id,
        "plugin_id": pv.plugin_id,
        "version": pv.version,
        "tarball_sha256": pv.tarball_sha256,
        "package_json": pkg_snapshot,
        "changelog": pv.changelog,
        "submit_source": pv.submit_source,
        "review_status": pv.review_status,
        "has_lifecycle_scripts": bool(pv.has_lifecycle_scripts),
        "reviewed_by": pv.reviewed_by,
        "review_comment": pv.review_comment,
        "published_at": pv.published_at.isoformat() if pv.published_at else None,
        "created_at": pv.created_at.isoformat() if pv.created_at else None,
    }


def _serialize_plugin(
    plugin: Plugin,
    *,
    versions: Optional[List[PluginVersion]] = None,
    public_base: str = "",
) -> Dict[str, Any]:
    tags = _parse_tags(plugin.tags_json)
    item: Dict[str, Any] = {
        "id": plugin.id,
        "name": plugin.name,
        "display_name": plugin.display_name or plugin.name,
        "description": plugin.description,
        "category": plugin.category,
        "tags": tags,
        "icon": plugin.icon,
        "author_emp_no": plugin.author_emp_no,
        "author_name": plugin.author_name or plugin.author_emp_no,
        "repo_url": plugin.repo_url,
        "status": plugin.status,
        "latest_version": plugin.latest_version,
        "downloads": plugin.downloads,
        "sort_weight": plugin.sort_weight,
        "created_at": plugin.created_at.isoformat() if plugin.created_at else None,
        "updated_at": plugin.updated_at.isoformat() if plugin.updated_at else None,
    }
    if public_base:
        item["install_command"] = f"dsh plugin install {plugin.name} --registry {public_base}/npm"
    if versions is not None:
        item["versions"] = [_serialize_version(v) for v in versions]
    return item


@public_market_router.get("/market/index.json", summary="DSH 插件市场 Format-1 标准索引")
def get_dsh_market_index(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """免登录只读输出 @deepseek-ai/dsh-plugin-market Format-1 JSON"""
    public_base = _resolve_public_base(request)
    registry_url = f"{public_base}/npm"

    published_plugins = (
        db.query(Plugin)
        .filter(Plugin.status == "published")
        .order_by(Plugin.sort_weight.desc(), Plugin.downloads.desc(), Plugin.id.desc())
        .all()
    )

    categories: List[str] = []
    seen_cats = set()
    plugins_out: List[Dict[str, Any]] = []
    for p in published_plugins:
        cat = p.category or "效率工具"
        if cat not in seen_cats:
            seen_cats.add(cat)
            categories.append(cat)
        plugins_out.append({
            "name": p.name,
            "displayName": p.display_name or p.name,
            "description": p.description or "",
            "category": cat,
            "tags": _parse_tags(p.tags_json),
            "icon": p.icon or "Puzzle",
            "version": p.latest_version or "0.0.0",
            "author": p.author_name or p.author_emp_no,
            "repoUrl": p.repo_url or "",
            "downloads": p.downloads,
            "updatedAt": p.updated_at.isoformat() if p.updated_at else None,
        })

    return {
        "version": 1,
        "registry": registry_url,
        "categories": categories,
        "plugins": plugins_out,
    }


@portal_market_router.get("/plugins", summary="门户查询已上架插件列表")
def list_portal_plugins(
    request: Request,
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    public_base = _resolve_public_base(request)
    query = db.query(Plugin).filter(Plugin.status == "published")
    if category and category != "全部":
        query = query.filter(Plugin.category == category)

    plugins = query.order_by(
        Plugin.sort_weight.desc(), Plugin.downloads.desc(), Plugin.id.desc()
    ).all()

    kw = (q or "").strip().lower()
    if kw:
        plugins = [
            p
            for p in plugins
            if kw in p.name.lower()
            or kw in (p.display_name or "").lower()
            or kw in (p.description or "").lower()
            or kw in (p.tags_json or "").lower()
        ]

    all_published = db.query(Plugin).filter(Plugin.status == "published").all()
    categories = sorted({p.category or "效率工具" for p in all_published})

    return {
        "registry": f"{public_base}/npm",
        "market_url": f"{public_base}/market/index.json",
        "categories": categories,
        "items": [_serialize_plugin(p, public_base=public_base) for p in plugins],
    }


@portal_market_router.get("/plugins/{plugin_id}", summary="查询单个插件详情与版本历史")
def get_portal_plugin_detail(
    plugin_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
    if not plugin or plugin.status != "published":
        raise HTTPException(status_code=404, detail="插件不存在或未上架")

    versions = (
        db.query(PluginVersion)
        .filter(PluginVersion.plugin_id == plugin.id, PluginVersion.review_status == "approved")
        .order_by(PluginVersion.id.desc())
        .all()
    )
    return _serialize_plugin(plugin, versions=versions, public_base=_resolve_public_base(request))


@portal_market_router.post("/plugins/{plugin_id}/download-hit", summary="记录插件安装命令使用次数")
def record_plugin_download_hit(plugin_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    plugin.downloads = int(plugin.downloads or 0) + 1
    db.commit()
    return {"id": plugin.id, "downloads": plugin.downloads}


@portal_market_router.get("/my-submissions", summary="查询当前员工的插件投稿与审核状态")
def list_my_plugin_submissions(
    request: Request,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    public_base = _resolve_public_base(request)
    my_plugins = (
        db.query(Plugin)
        .filter(Plugin.author_emp_no == employee.emp_no)
        .order_by(Plugin.updated_at.desc(), Plugin.id.desc())
        .all()
    )
    items = []
    for p in my_plugins:
        versions = (
            db.query(PluginVersion)
            .filter(PluginVersion.plugin_id == p.id)
            .order_by(PluginVersion.id.desc())
            .all()
        )
        items.append(_serialize_plugin(p, versions=versions, public_base=public_base))
    return {"items": items}


@portal_market_router.post("/submissions", summary="员工投稿新插件或新版本")
async def submit_plugin(
    request: Request,
    submit_source: str = Form("tgz"),
    display_name: str = Form(""),
    description: str = Form(""),
    category: str = Form("效率工具"),
    tags: str = Form(""),
    icon: str = Form("Puzzle"),
    name: str = Form(""),
    version: str = Form(""),
    repo_url: str = Form(""),
    changelog: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    source = submit_source.strip().lower()
    if source not in ("tgz", "git"):
        raise HTTPException(status_code=400, detail="submit_source 必须为 tgz 或 git")

    tarball_path_str = ""
    tarball_sha256 = ""
    pkg_snapshot: Dict[str, Any] = {}
    has_lifecycle_scripts = False

    if source == "tgz":
        if file is None:
            raise HTTPException(status_code=400, detail="请上传 .tgz 插件压缩包")
        raw_bytes = await file.read()
        try:
            validated = validate_plugin_tgz(raw_bytes, allow_lifecycle_scripts=False)
        except PluginValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        pkg_name = validated.name
        pkg_version = validated.version
        pkg_desc = description.strip() or validated.description
        tarball_sha256 = validated.sha256
        pkg_snapshot = validated.package_json
        has_lifecycle_scripts = validated.has_lifecycle_scripts

        safe_dir_name = pkg_name.replace("@", "").replace("/", "__")
        target_dir = settings.resolved_plugins_dir / safe_dir_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{safe_dir_name}-{pkg_version}.tgz"
        target_file.write_bytes(raw_bytes)
        tarball_path_str = str(target_file)
    else:
        clean_repo = repo_url.strip()
        if not clean_repo or not (clean_repo.startswith("http://") or clean_repo.startswith("https://") or clean_repo.startswith("git@")):
            raise HTTPException(status_code=400, detail="Git 仓库投稿需填写合法的 HTTP/HTTPS/SSH 仓库地址")
        try:
            pkg_name = validate_package_name(name)
            pkg_version = validate_semver(version)
        except PluginValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        pkg_desc = description.strip()
        pkg_snapshot = {
            "name": pkg_name,
            "version": pkg_version,
            "description": pkg_desc,
            "repository": clean_repo,
        }

    existing_plugin = db.query(Plugin).filter(Plugin.name == pkg_name).first()
    if existing_plugin and existing_plugin.author_emp_no != employee.emp_no:
        raise HTTPException(
            status_code=403,
            detail=f"插件包 {pkg_name} 已由其他员工 ({existing_plugin.author_emp_no}) 维护，禁止越权覆盖",
        )

    tags_list = _parse_tags_input(tags)
    if not existing_plugin:
        existing_plugin = Plugin(
            name=pkg_name,
            display_name=display_name.strip() or pkg_name.split("/")[-1],
            description=pkg_desc,
            category=category.strip() or "效率工具",
            tags_json=json.dumps(tags_list, ensure_ascii=False),
            icon=icon.strip() or "Puzzle",
            author_emp_no=employee.emp_no,
            author_name=employee.name,
            repo_url=repo_url.strip(),
            status="pending",
        )
        db.add(existing_plugin)
        db.flush()
    else:
        dup = (
            db.query(PluginVersion)
            .filter(
                PluginVersion.plugin_id == existing_plugin.id,
                PluginVersion.version == pkg_version,
                PluginVersion.review_status.in_(["pending", "approved"]),
            )
            .first()
        )
        if dup:
            raise HTTPException(
                status_code=409,
                detail=f"{pkg_name}@{pkg_version} 已提交或已发布，请递增版本号后重投",
            )
        if display_name.strip():
            existing_plugin.display_name = display_name.strip()
        if pkg_desc:
            existing_plugin.description = pkg_desc
        if category.strip():
            existing_plugin.category = category.strip()
        if tags_list:
            existing_plugin.tags_json = json.dumps(tags_list, ensure_ascii=False)
        if repo_url.strip():
            existing_plugin.repo_url = repo_url.strip()
        if existing_plugin.status == "rejected":
            existing_plugin.status = "pending"

    pv = PluginVersion(
        plugin_id=existing_plugin.id,
        version=pkg_version,
        tarball_path=tarball_path_str,
        tarball_sha256=tarball_sha256,
        package_json_snapshot=json.dumps(pkg_snapshot, ensure_ascii=False),
        changelog=changelog.strip(),
        submit_source=source,
        review_status="pending",
        has_lifecycle_scripts=has_lifecycle_scripts,
    )
    db.add(pv)
    db.commit()
    db.refresh(existing_plugin)
    db.refresh(pv)

    # 非阻塞推送审核提醒给配置的小秘书审核员
    reviewers = settings.plugin_reviewer_list
    if reviewers:
        await XiaomishuService.notify_users(
            db,
            reviewers,
            [
                f"【DSH 插件审核提醒】员工 {employee.name}({employee.emp_no}) 提交了插件 {pkg_name}@{pkg_version}（{source}），请前往后台「插件市场治理」审核。"
            ],
        )

    return {
        "message": "插件投稿已提交，待管理员审核通过后自动发布上架",
        "plugin": _serialize_plugin(
            existing_plugin,
            versions=[pv],
            public_base=_resolve_public_base(request),
        ),
    }


# ============================================================================
# 管理端插件市场治理 API
# ============================================================================


class ReviewApproveRequest(BaseModel):
    comment: str = ""
    allow_lifecycle_scripts: bool = False


class ReviewRejectRequest(BaseModel):
    comment: str = Field(..., min_length=1, description="驳回原因")


class AdminPluginUpdateRequest(BaseModel):
    status: Optional[str] = None
    sort_weight: Optional[int] = None
    category: Optional[str] = None
    display_name: Optional[str] = None


@admin_plugins_router.get("", summary="管理端查询全部插件与版本审核队列")
def admin_list_plugins(
    request: Request,
    status_filter: str = Query(default="all"),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _ = admin
    public_base = _resolve_public_base(request)
    plugins = db.query(Plugin).order_by(Plugin.sort_weight.desc(), Plugin.updated_at.desc(), Plugin.id.desc()).all()
    items = []
    for p in plugins:
        versions = (
            db.query(PluginVersion)
            .filter(PluginVersion.plugin_id == p.id)
            .order_by(PluginVersion.id.desc())
            .all()
        )
        if status_filter == "pending":
            if not any(v.review_status == "pending" for v in versions):
                continue
        elif status_filter != "all" and p.status != status_filter:
            continue
        items.append(_serialize_plugin(p, versions=versions, public_base=public_base))
    return {"items": items}


@admin_plugins_router.post("/versions/{version_id}/approve", summary="管理员审核通过并自动推送到 Verdaccio")
async def admin_approve_plugin_version(
    version_id: int,
    body: ReviewApproveRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    pv = db.query(PluginVersion).filter(PluginVersion.id == version_id).first()
    if not pv:
        raise HTTPException(status_code=404, detail="插件版本不存在")

    plugin = db.query(Plugin).filter(Plugin.id == pv.plugin_id).first()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件主记录不存在")

    if pv.has_lifecycle_scripts and not body.allow_lifecycle_scripts:
        raise HTTPException(
            status_code=400,
            detail="该版本包含生命周期脚本，需管理员显式勾选放行后才能审核发布",
        )

    publish_status = "git_approved"
    if pv.tarball_path:
        tarball_file = Path(pv.tarball_path)
        if not tarball_file.is_file():
            raise HTTPException(status_code=500, detail="本地插件压缩包文件缺失，无法推送")
        try:
            pkg_json = json.loads(pv.package_json_snapshot or "{}")
        except Exception:
            pkg_json = {"name": plugin.name, "version": pv.version}
        public_registry = f"{_resolve_public_base(request)}/npm"
        ok, msg = await VerdaccioPublisher.publish_tarball(
            package_name=plugin.name,
            version=pv.version,
            tarball_bytes=tarball_file.read_bytes(),
            package_json=pkg_json,
            public_registry_url=public_registry,
        )
        if not ok:
            raise HTTPException(status_code=502, detail=msg)
        publish_status = msg

    now = datetime.utcnow()
    pv.review_status = "approved"
    pv.reviewed_by = admin.username
    pv.review_comment = body.comment.strip() or "审核通过并已发布"
    pv.published_at = now

    plugin.status = "published"
    plugin.latest_version = pv.version
    db.commit()
    db.refresh(plugin)
    db.refresh(pv)

    await XiaomishuService.notify_users(
        db,
        [plugin.author_emp_no],
        [
            f"【DSH 插件审核通过】您提交的插件 {plugin.name}@{pv.version} 已审核通过并上线插件市场。批注：{pv.review_comment}"
        ],
    )

    return {
        "message": "审核通过并已发布上线",
        "publish_status": publish_status,
        "plugin": _serialize_plugin(plugin, versions=[pv], public_base=_resolve_public_base(request)),
    }


@admin_plugins_router.post("/versions/{version_id}/reject", summary="管理员驳回插件版本投稿")
async def admin_reject_plugin_version(
    version_id: int,
    body: ReviewRejectRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    pv = db.query(PluginVersion).filter(PluginVersion.id == version_id).first()
    if not pv:
        raise HTTPException(status_code=404, detail="插件版本不存在")

    plugin = db.query(Plugin).filter(Plugin.id == pv.plugin_id).first()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件主记录不存在")

    pv.review_status = "rejected"
    pv.reviewed_by = admin.username
    pv.review_comment = body.comment.strip()
    if not plugin.latest_version:
        plugin.status = "rejected"

    db.commit()
    db.refresh(plugin)
    db.refresh(pv)

    await XiaomishuService.notify_users(
        db,
        [plugin.author_emp_no],
        [
            f"【DSH 插件审核驳回】您提交的插件 {plugin.name}@{pv.version} 未通过审核，原因：{pv.review_comment}"
        ],
    )

    return {
        "message": "已驳回该插件版本投稿",
        "plugin": _serialize_plugin(plugin, versions=[pv], public_base=_resolve_public_base(request)),
    }


@admin_plugins_router.patch("/{plugin_id}", summary="更新插件上架状态、排序权重或分类")
def admin_update_plugin(
    plugin_id: int,
    body: AdminPluginUpdateRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _ = admin
    plugin = db.query(Plugin).filter(Plugin.id == plugin_id).first()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")

    if body.status is not None:
        if body.status not in ("published", "deprecated", "pending", "rejected"):
            raise HTTPException(status_code=400, detail="不支持的状态值")
        plugin.status = body.status
    if body.sort_weight is not None:
        plugin.sort_weight = body.sort_weight
    if body.category is not None and body.category.strip():
        plugin.category = body.category.strip()
    if body.display_name is not None and body.display_name.strip():
        plugin.display_name = body.display_name.strip()

    db.commit()
    db.refresh(plugin)
    return _serialize_plugin(plugin, public_base=_resolve_public_base(request))
