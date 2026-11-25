from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.api.deps import get_current_employee
from backend.app.models.employee import Employee
from backend.app.services.log_sync import LogSyncService

router = APIRouter(prefix="/me/usage", tags=["员工个人用量看板"])


@router.get("/overview", summary="获取员工核心用量 KPI 指标")
def get_usage_overview(
    range: str = Query("7d", pattern="^(today|7d|30d|all)$"),
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """返回总请求次数、总 Token、输入/输出 Token 拆解、平均耗时、最常用模型"""
    return {
        "success": True,
        "data": LogSyncService.get_user_overview(db, current_user.emp_no, range)
    }


@router.get("/trend", summary="获取时间趋势折线/柱状图数据")
def get_usage_trend(
    range: str = Query("7d", pattern="^(today|7d|30d|all)$"),
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """
    时间序列趋势：
    - today: 按每小时聚合
    - 7d / 30d / all: 按自然日聚合
    """
    return {
        "success": True,
        "data": LogSyncService.get_user_trend(db, current_user.emp_no, range)
    }


@router.get("/models", summary="获取模型调用占比与消耗分布")
def get_usage_models(
    range: str = Query("7d", pattern="^(today|7d|30d|all)$"),
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """按模型分组统计调用次数、Token 占比与平均响应时间"""
    return {
        "success": True,
        "data": LogSyncService.get_user_model_distribution(db, current_user.emp_no, range)
    }


@router.get("/logs", summary="分页检索调用明细记录")
def get_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    model_name: Optional[str] = Query(None),
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """分页查看每条调用的输入/输出 Token、耗时与流式状态"""
    return {
        "success": True,
        "data": LogSyncService.get_user_logs_paginated(
            db=db,
            emp_no=current_user.emp_no,
            page=page,
            page_size=page_size,
            model_name=model_name
        )
    }


@router.post("/sync", summary="员工主动刷新个人用量数据")
async def trigger_sync(
    current_user: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    message, last_sync_time = await LogSyncService.refresh_employee_usage(db, current_user.emp_no)
    return {
        "success": True,
        "message": message,
        "last_successful_sync_time": last_sync_time,
        "sync_frequency": "后台每 5 分钟自动增量同步",
    }
