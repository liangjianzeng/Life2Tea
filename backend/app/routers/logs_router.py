"""
logs_router.py — Log Query & Maintenance API.

Endpoints:
  GET  /api/logs/days
  GET  /api/logs/files
  POST /api/logs/query
  GET  /api/logs/summary
  POST /api/logs/delete
  POST /api/logs/cleanup
  POST /api/logs/archive
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List


router = APIRouter()


class QueryBody(BaseModel):
    date_from: str
    date_to: Optional[str] = None
    level: Optional[str] = None
    module: Optional[str] = None
    model: Optional[str] = None
    plugin: Optional[str] = None
    keyword: Optional[str] = None
    limit: int = 500
    offset: int = 0
    order: str = "desc"


class DeleteBody(BaseModel):
    day: str


class CleanupBody(BaseModel):
    days: int = 30


class ArchiveBody(BaseModel):
    day: str
    delete_source: bool = True


@router.get("/days")
async def list_days(include_archive: bool = True):
    from ..main import get_logger_mgr
    mgr = get_logger_mgr()
    return {"days": mgr.list_days(include_archive=include_archive)}


@router.get("/files")
async def list_files(include_archive: bool = True):
    from ..main import get_logger_mgr
    mgr = get_logger_mgr()
    return {"files": mgr.list_log_files(include_archive=include_archive)}


@router.post("/query")
async def query_logs(body: QueryBody):
    from ..main import get_logger_mgr
    mgr = get_logger_mgr()
    return mgr.query(
        date_from=body.date_from,
        date_to=body.date_to,
        level=body.level,
        module=body.module,
        model=body.model,
        plugin=body.plugin,
        keyword=body.keyword,
        limit=body.limit,
        offset=body.offset,
        order=body.order,
    )


@router.get("/summary")
async def get_log_summary(days: int = 7):
    from ..main import get_logger_mgr
    mgr = get_logger_mgr()
    return mgr.summary(days=days)


@router.post("/delete")
async def delete_logs(body: DeleteBody):
    from ..main import get_logger_mgr
    mgr = get_logger_mgr()
    ok = mgr.delete_day(body.day)
    return {"ok": ok}


@router.post("/cleanup")
async def cleanup_logs(body: CleanupBody):
    from ..main import get_logger_mgr
    mgr = get_logger_mgr()
    return mgr.cleanup_before(body.days)


@router.post("/archive")
async def archive_logs(body: ArchiveBody):
    from ..main import get_logger_mgr
    mgr = get_logger_mgr()
    return mgr.archive_day(body.day, delete_source=body.delete_source)
