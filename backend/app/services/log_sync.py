from __future__ import annotations
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from hashlib import blake2b
from tempfile import TemporaryFile
from typing import Dict, List, Literal, Optional, Tuple
from uuid import uuid4
from fastapi import HTTPException, status
from sqlalchemy import func, insert, literal, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.core.database import SessionLocal
from backend.app.models.employee import Employee
from backend.app.models.log_cache import UsageLogCache
from backend.app.models.token import UserToken
from backend.app.models.setting import SystemSetting
from backend.app.services.new_api_client import new_api_client

logger = logging.getLogger("log_sync")

UsageRankingDimension = Literal["user", "model"]
UsageRankingRange = Literal["today", "7d", "30d", "all"]
SHANGHAI_TIME = timezone(timedelta(hours=8))

class LogSyncService:
    """日志增量同步与多维统计聚合引擎"""

    _LOCK_KEY = "log_sync_lease"
    _LOCK_DURATION = timedelta(seconds=120)
    _SOURCE_KEY = "usage_log_source_version"
    _SOURCE_VERSION = "admin-v1"
    _PERSONAL_REFRESH_INTERVAL = timedelta(seconds=10)

    @staticmethod
    def _log_row(item: dict, token_map: dict[str, str], *, real: bool) -> dict:
        token_name = item.get("token_name", "").strip()
        emp_no = token_map.get(token_name)
        if not emp_no:
            match = re.match(r"^EMP_([a-zA-Z0-9_\-]+)_", token_name)
            emp_no = match.group(1) if match else "UNKNOWN"

        # ClickHouse log lists also use display IDs. Prefer the request ID
        # when present and keep real identities outside the old cache's range.
        request_id = item.get("request_id")
        if real and request_id:
            digest = blake2b(request_id.encode("utf-8"), digest_size=8).digest()
            log_id = -(int.from_bytes(digest, "big") & ((1 << 62) - 1)) - (1 << 62)
        else:
            log_id = int(item["id"])
            if log_id <= 0 or (real and log_id >= 1 << 62):
                raise ValueError("网关返回的日志标识无效")
            if real:
                log_id = -log_id

        return {
            "new_api_log_id": log_id,
            "token_name": token_name,
            "emp_no": emp_no,
            "model_name": item.get("model_name", "unknown"),
            "prompt_tokens": item.get("prompt_tokens", 0),
            "completion_tokens": item.get("completion_tokens", 0),
            "quota": item.get("quota", 0),
            "use_time": item.get("use_time", 0),
            "is_stream": bool(item.get("is_stream", False)),
            "created_at": int(item["created_at"]),
        }

    @staticmethod
    def _store_log_rows(db: Session, rows: list[dict]) -> int:
        identities = {row["new_api_log_id"]: row for row in rows}
        existing = db.query(UsageLogCache.new_api_log_id).filter(
            UsageLogCache.new_api_log_id.in_(list(identities))
        )
        for (identity,) in existing:
            identities.pop(identity)
        if identities:
            db.execute(insert(UsageLogCache), list(identities.values()))
        return len(identities)

    @classmethod
    def _acquire_sync_lock(cls, db: Session) -> Optional[str]:
        owner = uuid4().hex
        now = datetime.utcnow()
        changed = db.query(SystemSetting).filter(
            SystemSetting.key == cls._LOCK_KEY,
            or_(SystemSetting.value.is_(None), SystemSetting.updated_at <= now - cls._LOCK_DURATION),
        ).update({"value": owner, "updated_at": now}, synchronize_session=False)
        if changed == 1:
            db.commit()
            return owner

        if not db.query(SystemSetting.key).filter_by(key=cls._LOCK_KEY).first():
            db.add(SystemSetting(key=cls._LOCK_KEY, value=owner, updated_at=now))
            try:
                db.commit()
                return owner
            except IntegrityError:
                db.rollback()
                return None
        db.rollback()
        return None

    @classmethod
    def _renew_sync_lock(cls, db: Session, owner: str) -> bool:
        # Callers commit the renewal together with any protected writes.
        now = datetime.utcnow()
        changed = db.query(SystemSetting).filter(
            SystemSetting.key == cls._LOCK_KEY,
            SystemSetting.value == owner,
            SystemSetting.updated_at > now - cls._LOCK_DURATION,
        ).update({"updated_at": now}, synchronize_session=False)
        return changed == 1

    @classmethod
    def _release_sync_lock(cls, db: Session, owner: str):
        try:
            db.query(SystemSetting).filter(
                SystemSetting.key == cls._LOCK_KEY,
                SystemSetting.value == owner,
            ).update({"value": None}, synchronize_session=False)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"释放同步锁异常: {e}")

    @classmethod
    def _require_sync_lock(cls, db: Session, owner: str):
        if not cls._renew_sync_lock(db, owner):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="日志同步租约已失效，请重新触发")

    @classmethod
    async def sync_incremental_logs(cls, db: Optional[Session] = None) -> int:
        """
        从上次记录的 last_log_sync_ts 增量拉取 new-api 消费日志 (type=2)
        解析映射 emp_no 并幂等写入 usage_logs_cache 表
        带全局单例互斥锁与 120 秒超时接管
        """
        close_db_when_done = False
        if db is None:
            db = SessionLocal()
            close_db_when_done = True

        owner = None
        replay = None
        try:
            owner = cls._acquire_sync_lock(db)
            if owner is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="全行日志增量同步正在进行中，请勿重复触发"
                )

            # 1. 获取上次同步时间戳
            ts_setting = db.query(SystemSetting).filter(SystemSetting.key == "last_log_sync_ts").first()
            last_ts = int(ts_setting.value) if (ts_setting and ts_setting.value) else 0
            real = not new_api_client.is_mock
            source = db.get(SystemSetting, cls._SOURCE_KEY) if real else None
            rebuild = real and (source is None or source.value != cls._SOURCE_VERSION)
            fetch_options = {}
            if rebuild:
                replay = TemporaryFile(mode="w+t", encoding="utf-8")
                fetch_options["end_timestamp"] = int(time.time()) - 1
                last_ts = 0

            # 2. 从 new-api 分页拉取所有新日志
            page = 1
            page_size = 100
            new_records_count = 0
            max_log_ts = last_ts
            oldest_log_ts = None

            # 构建本地已有的 token 映射缓存 {token_name: emp_no}
            tokens = db.query(UserToken.token_name, UserToken.emp_no).all()
            token_map = {t[0]: t[1] for t in tokens}

            while True:
                cls._require_sync_lock(db, owner)
                db.commit()
                raw_logs = await new_api_client.fetch_consumption_logs(
                    start_timestamp=last_ts,
                    page=page,
                    page_size=page_size,
                    **fetch_options,
                )
                if not raw_logs:
                    break

                cls._require_sync_lock(db, owner)
                timestamps = [int(item["created_at"]) for item in raw_logs]
                rows = [
                    cls._log_row(item, token_map, real=real)
                    for item in raw_logs
                    if not real or (
                        item.get("token_name", "").strip() in token_map
                        and (item.get("user_id") is None or str(item["user_id"]) == str(new_api_client.user_id))
                    )
                ]
                max_log_ts = max(max_log_ts, max(timestamps))
                if replay is not None:
                    page_oldest = min(timestamps)
                    oldest_log_ts = page_oldest if oldest_log_ts is None else min(oldest_log_ts, page_oldest)
                    replay.write(json.dumps(rows) + "\n")
                else:
                    new_records_count += cls._store_log_rows(db, rows)

                db.commit()

                # 如果当页不满 page_size，说明已经拉取到最新
                if len(raw_logs) < page_size:
                    break
                page += 1

            # 3. 整轮分页成功后推进 last_log_sync_ts 游标
            cls._require_sync_lock(db, owner)
            if replay is not None:
                legacy = db.query(UsageLogCache).filter(UsageLogCache.new_api_log_id > 0)
                if oldest_log_ts is not None:
                    # Retain cache entries older than the history still available from the gateway.
                    legacy.filter(UsageLogCache.created_at >= oldest_log_ts).delete(synchronize_session=False)
                    replay.seek(0)
                    for batch in replay:
                        new_records_count += cls._store_log_rows(db, json.loads(batch))
                elif legacy.first():
                    raise RuntimeError("网关未返回消费日志，已保留原用量缓存")
                if source is None:
                    source = SystemSetting(key=cls._SOURCE_KEY)
                    db.add(source)
                source.value = cls._SOURCE_VERSION

            if rebuild or max_log_ts > last_ts:
                if not ts_setting:
                    ts_setting = SystemSetting(key="last_log_sync_ts")
                    db.add(ts_setting)
                ts_setting.value = str(max_log_ts)

            # 记录最近同步成功元数据
            cls._record_sync_result(db, success=True, message=f"同步完成，新增 {new_records_count} 条记录")
            db.commit()

            logger.info(f"增量日志同步完成，新增入库记录数: {new_records_count}")
            return new_records_count

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            err_msg = str(e)
            logger.error(f"增量同步消费日志异常: {err_msg}")
            if owner is not None:
                try:
                    if cls._renew_sync_lock(db, owner):
                        cls._record_sync_result(db, success=False, message=err_msg)
                        db.commit()
                except Exception as record_error:
                    logger.warning(f"记录同步结果元数据失败: {record_error}")
                finally:
                    db.rollback()
            raise RuntimeError(f"增量同步消费日志失败: {err_msg}") from e
        finally:
            db.rollback()
            if replay is not None:
                replay.close()
            if owner is not None:
                cls._release_sync_lock(db, owner)
            if close_db_when_done:
                db.close()

    @classmethod
    def _record_sync_result(cls, db: Session, success: bool, message: str):
        """记录最近一次网关增量同步的结果与时间"""
        now_iso = datetime.now(SHANGHAI_TIME).strftime("%Y-%m-%d %H:%M:%S")
        records = [
            ("last_sync_status", "success" if success else "failed"),
            ("last_sync_time", now_iso),
            ("last_sync_message", message[:255]),
        ]
        if success:
            records.append(("last_successful_sync_time", now_iso))

        for k, v in records:
            rec = db.get(SystemSetting, k)
            if not rec:
                db.add(SystemSetting(key=k, value=v))
            else:
                rec.value = v

    @classmethod
    def get_last_successful_sync_time(cls, db: Session) -> str:
        """获取最近一次全行成功同步的时间戳字符串"""
        rec = db.query(SystemSetting).filter(SystemSetting.key == "last_successful_sync_time").first()
        if rec and rec.value:
            return rec.value
        return ""

    @classmethod
    async def refresh_employee_usage(cls, db: Session, emp_no: str) -> tuple[str, str]:
        def cached(message: str) -> tuple[str, str]:
            return message, cls.get_last_successful_sync_time(db)

        if new_api_client.is_mock:
            return cached("已刷新本地用量")
        token = db.query(UserToken.token_name, UserToken.new_api_token_id).filter_by(emp_no=emp_no).first()
        if not token or not token.new_api_token_id:
            return cached("尚未领取个人令牌")
        owner = cls._acquire_sync_lock(db)
        if owner is None:
            return cached("网关日志正在同步，已显示当前用量")
        try:
            legacy = db.query(UsageLogCache.id).filter(UsageLogCache.new_api_log_id > 0)
            if db.get(SystemSetting, cls._SOURCE_KEY) is None and legacy.first():
                return cached("历史用量待回补，已显示当前数据")

            refresh_key = "usage_refresh_" + blake2b(emp_no.encode("utf-8"), digest_size=16).hexdigest()
            now = datetime.utcnow()
            attempt = db.get(SystemSetting, refresh_key)
            if attempt and now - attempt.updated_at < cls._PERSONAL_REFRESH_INTERVAL:
                return cached("已显示当前用量，请稍后再同步")
            if attempt is None:
                attempt = SystemSetting(key=refresh_key)
                db.add(attempt)
            attempt.updated_at = now
            db.commit()

            token_name, token_id = token
            raw_logs = await new_api_client.fetch_consumption_logs(
                start_timestamp=int(time.time()) - 86400, token_name=token_name
            )
            cls._require_sync_lock(db, owner)
            rows = [
                cls._log_row(item, {token_name: emp_no}, real=True)
                for item in raw_logs
                if item.get("token_name") == token_name
                and str(item.get("token_id")) == str(token_id)
            ]
            cls._store_log_rows(db, rows)
            db.commit()
            sync_time = datetime.now(SHANGHAI_TIME).strftime("%Y-%m-%d %H:%M:%S")
            return "已同步个人近期用量", sync_time
        except HTTPException:
            raise
        except Exception as error:
            logger.warning("同步个人用量失败: %s", error)
            raise HTTPException(status_code=502, detail="网关用量同步失败，请稍后重试") from error
        finally:
            db.rollback()
            cls._release_sync_lock(db, owner)

    @classmethod
    async def trigger_admin_sync(cls, db: Session) -> Tuple[bool, str, int]:
        """
        管理员仪表盘「立即拉取日志」触发：
        具备单例互斥锁，多请求并发返回正在同步
        """
        try:
            added = await cls.sync_incremental_logs(db)
            return True, f"网关日志同步成功，本次新增入库 {added} 条记录", added
        except Exception as e:
            err_text = str(e)
            if "正在进行中" in err_text:
                return False, err_text, 0
            return False, f"日志同步失败: {err_text}", 0

    @classmethod
    def get_department_usage_ranking(cls, db: Session) -> List[Dict[str, Any]]:
        """
        全行部门用量排行聚合：按部门统计 Token 消耗总数、调用频次与员工人数
        """
        total_tokens = func.coalesce(func.sum(UsageLogCache.prompt_tokens + UsageLogCache.completion_tokens), 0)
        query = (
            db.query(
                Employee.department,
                total_tokens.label("total_tokens"),
                func.coalesce(func.count(UsageLogCache.id), 0).label("request_count"),
                func.coalesce(func.count(func.distinct(Employee.emp_no)), 0).label("active_employees"),
            )
            .outerjoin(UsageLogCache, Employee.emp_no == UsageLogCache.emp_no)
            .filter(Employee.is_active.is_(True))
            .group_by(Employee.department)
            .order_by(total_tokens.desc())
            .all()
        )

        ranking = []
        for row in query:
            ranking.append({
                "department": row.department or "未分配部门",
                "total_tokens": int(row.total_tokens),
                "request_count": int(row.request_count),
                "active_employees": int(row.active_employees),
            })
        return ranking

    @classmethod
    def get_time_range_filter(cls, time_range: str, tz: Optional[timezone] = None) -> int:
        """计算统计周期起始时间戳。"""
        now = datetime.now(tz)
        if time_range in ("today", "month"):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if time_range == "month":
                start = start.replace(day=1)
            return int(start.timestamp())
        if time_range == "7d":
            return int(now.timestamp() - 7 * 86400)
        if time_range == "30d":
            return int(now.timestamp() - 30 * 86400)
        return 0

    @classmethod
    def get_usage_ranking(
        cls, db: Session, dimension: UsageRankingDimension, time_range: UsageRankingRange
    ) -> List[dict]:
        """按员工或模型汇总已同步的输入与输出 Token。"""
        by_user = dimension == "user"
        key = UsageLogCache.emp_no if by_user else UsageLogCache.model_name
        total_tokens = func.sum(UsageLogCache.prompt_tokens + UsageLogCache.completion_tokens)
        query = db.query(
            key.label("key"),
            func.sum(UsageLogCache.prompt_tokens).label("prompt_tokens"),
            func.sum(UsageLogCache.completion_tokens).label("completion_tokens"),
            total_tokens.label("total_tokens"),
            func.count(UsageLogCache.id).label("request_count"),
        ).select_from(UsageLogCache)

        if by_user:
            query = (
                query.add_columns(Employee.name, Employee.department)
                .outerjoin(Employee, Employee.emp_no == UsageLogCache.emp_no)
                .filter(UsageLogCache.emp_no.notin_(("", "UNKNOWN")))
                .group_by(key, Employee.name, Employee.department)
            )
        else:
            query = query.add_columns(key.label("name"), literal(None).label("department")).group_by(key)

        start_ts = cls.get_time_range_filter(time_range, tz=SHANGHAI_TIME)
        if start_ts:
            query = query.filter(UsageLogCache.created_at >= start_ts)

        rows = query.having(total_tokens > 0).order_by(total_tokens.desc(), key.asc()).limit(20).all()
        return [
            {
                "key": row.key,
                "name": row.name or row.key,
                "department": row.department,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "total_tokens": row.total_tokens,
                "request_count": row.request_count,
            }
            for row in rows
        ]

    @classmethod
    def get_user_overview(cls, db: Session, emp_no: str, time_range: str = "7d") -> dict:
        """计算员工在指定周期内的核心 KPI"""
        start_ts = cls.get_time_range_filter(time_range, tz=SHANGHAI_TIME)

        query = db.query(UsageLogCache).filter(UsageLogCache.emp_no == emp_no)
        if start_ts > 0:
            query = query.filter(UsageLogCache.created_at >= start_ts)

        total_requests = query.count()
        if total_requests == 0:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "avg_response_time": 0,
                "top_model": "-",
                "last_active_time": "-",
            }

        stats = db.query(
            func.sum(UsageLogCache.prompt_tokens).label("prompt_sum"),
            func.sum(UsageLogCache.completion_tokens).label("comp_sum"),
            func.avg(UsageLogCache.use_time).label("avg_time"),
            func.max(UsageLogCache.created_at).label("last_ts")
        ).filter(UsageLogCache.emp_no == emp_no)

        if start_ts > 0:
            stats = stats.filter(UsageLogCache.created_at >= start_ts)
        
        stat_res = stats.first()
        prompt_sum = int(stat_res.prompt_sum or 0)
        comp_sum = int(stat_res.comp_sum or 0)
        avg_time = int(stat_res.avg_time or 0)
        last_ts = int(stat_res.last_ts or 0)

        # 最常用模型
        top_model_q = db.query(
            UsageLogCache.model_name,
            func.count(UsageLogCache.id).label("cnt")
        ).filter(UsageLogCache.emp_no == emp_no)
        if start_ts > 0:
            top_model_q = top_model_q.filter(UsageLogCache.created_at >= start_ts)
        top_model_res = top_model_q.group_by(UsageLogCache.model_name).order_by(func.count(UsageLogCache.id).desc()).first()

        last_active_str = "-"
        if last_ts > 0:
            last_active_str = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "total_requests": total_requests,
            "total_tokens": prompt_sum + comp_sum,
            "prompt_tokens": prompt_sum,
            "completion_tokens": comp_sum,
            "avg_response_time": avg_time,
            "top_model": top_model_res[0] if top_model_res else "-",
            "last_active_time": last_active_str,
        }

    @classmethod
    def get_user_trend(cls, db: Session, emp_no: str, time_range: str = "7d") -> dict:
        """
        获取趋势图数据（SQL 粒度直接聚合，不将全文明细加载入 Python）：
        - today: 按 00:00 ~ 23:00 小时聚合
        - 7d / 30d / all: 按 YYYY-MM-DD 日聚合
        """
        start_ts = cls.get_time_range_filter(time_range)
        is_hourly = (time_range == "today")
        time_fmt = "%H:00" if is_hourly else "%Y-%m-%d"

        # SQLite 引擎层直接 strftime 分桶聚合
        bucket_col = func.strftime(time_fmt, func.datetime(UsageLogCache.created_at, "unixepoch", "localtime")).label("bucket")

        query = (
            db.query(
                bucket_col,
                func.count(UsageLogCache.id).label("requests"),
                func.coalesce(func.sum(UsageLogCache.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(UsageLogCache.completion_tokens), 0).label("completion_tokens"),
            )
            .filter(UsageLogCache.emp_no == emp_no)
        )

        if start_ts > 0:
            query = query.filter(UsageLogCache.created_at >= start_ts)

        rows = query.group_by(bucket_col).order_by(bucket_col.asc()).all()

        categories = []
        requests_series = []
        prompt_series = []
        comp_series = []
        total_series = []

        for r in rows:
            if not r[0]:
                continue
            b_name = str(r[0])
            p_tok = int(r[2] or 0)
            c_tok = int(r[3] or 0)
            categories.append(b_name)
            requests_series.append(int(r[1] or 0))
            prompt_series.append(p_tok)
            comp_series.append(c_tok)
            total_series.append(p_tok + c_tok)

        return {
            "categories": categories,
            "series": {
                "requests": requests_series,
                "prompt_tokens": prompt_series,
                "completion_tokens": comp_series,
                "total_tokens": total_series,
            }
        }

    @classmethod
    def get_user_model_distribution(cls, db: Session, emp_no: str, time_range: str = "7d") -> List[dict]:
        """模型调用次数与 Token 消耗分布"""
        start_ts = cls.get_time_range_filter(time_range)
        query = db.query(
            UsageLogCache.model_name,
            func.count(UsageLogCache.id).label("requests"),
            func.sum(UsageLogCache.prompt_tokens).label("prompt_tokens"),
            func.sum(UsageLogCache.completion_tokens).label("completion_tokens"),
            func.avg(UsageLogCache.use_time).label("avg_time")
        ).filter(UsageLogCache.emp_no == emp_no)

        if start_ts > 0:
            query = query.filter(UsageLogCache.created_at >= start_ts)

        results = query.group_by(UsageLogCache.model_name).order_by(func.count(UsageLogCache.id).desc()).all()

        return [
            {
                "model_name": r[0],
                "requests": int(r[1] or 0),
                "prompt_tokens": int(r[2] or 0),
                "completion_tokens": int(r[3] or 0),
                "total_tokens": int(r[2] or 0) + int(r[3] or 0),
                "avg_response_time": int(r[4] or 0),
            }
            for r in results
        ]

    @classmethod
    def get_user_logs_paginated(
        cls,
        db: Session,
        emp_no: str,
        page: int = 1,
        page_size: int = 15,
        model_name: Optional[str] = None
    ) -> dict:
        """分页明细查询"""
        query = db.query(UsageLogCache).filter(UsageLogCache.emp_no == emp_no)
        if model_name:
            query = query.filter(UsageLogCache.model_name == model_name)

        total = query.count()
        records = query.order_by(UsageLogCache.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for r in records:
            items.append({
                "id": r.id,
                "log_id": r.new_api_log_id,
                "model_name": r.model_name,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.prompt_tokens + r.completion_tokens,
                "use_time": r.use_time,
                "is_stream": r.is_stream,
                "created_at": datetime.fromtimestamp(r.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }
