from __future__ import annotations
from fastapi import APIRouter
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.me import router as me_router
from backend.app.api.v1.guide import router as guide_router
from backend.app.api.v1.admin import router as admin_router
from backend.app.api.v1.usage import router as usage_router
from backend.app.api.v1.files import router as files_router
from backend.app.api.v1.admin_employees import router as admin_employees_router
from backend.app.api.v1.admin_tokens import router as admin_tokens_router
from backend.app.api.v1.articles import router as articles_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth_router)
api_router.include_router(me_router)
api_router.include_router(usage_router)
api_router.include_router(guide_router)
api_router.include_router(files_router)
api_router.include_router(articles_router)
api_router.include_router(admin_router)
api_router.include_router(admin_employees_router)
api_router.include_router(admin_tokens_router)
