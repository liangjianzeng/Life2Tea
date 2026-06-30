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

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, List

from ..main import get_logger_mgr
from ..core.logger import LoggerManager


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


@router.get("/days", summary="List available log days")
async def list_days(
    include_archive: bool = True,
    mgr: LoggerManager = Depends(get_logger_mgr),
):
    days = mgr.list_days(include_archive=include_archive)
    mgr.info("router", f"Listed log days: {len(days)}")
    return {"days": days}


@router.get("/files", summary="List log files")
async def list_files(
    include_archive: bool = True,
    mgr: LoggerManager = Depends(get_logger_mgr),
):
    return {"files": mgr.list_log_files(include_archive=include_archive)}


@router.post("/query", summary="Query logs with filters")
async def query_logs(
    body: QueryBody,
    mgr: LoggerManager = Depends(get_logger_mgr),
):
    result = mgr.query(
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
    mgr.info("router", f"Query logs: {result['total']} entries from {body.date_from}")
    return result


@router.get("/summary", summary="Get log summary for recent days")
async def get_log_summary(
    days: int = 7,
    mgr: LoggerManager = Depends(get_logger_mgr),
):
    summary = mgr.summary(days=days)
    # Ensure days array is present (for frontend compatibility)
    if "days" not in summary:
        summary["days"] = []
    return summary


@router.post("/delete", summary="Delete log for a specific day")
async def delete_logs(
    body: DeleteBody,
    mgr: LoggerManager = Depends(get_logger_mgr),
):
    ok = mgr.delete_day(body.day)
    if ok:
        mgr.info("router", f"Deleted log file for {body.day}")
    else:
        mgr.warn("router", f"Failed to delete log file for {body.day}")
    return {"ok": ok}


@router.post("/cleanup", summary="Delete logs older than N days")
async def cleanup_logs(
    body: CleanupBody,
    mgr: LoggerManager = Depends(get_logger_mgr),
):
    result = mgr.cleanup_before(body.days)
    mgr.info("router", f"Cleanup: removed {result['count']} log files")
    return result


@router.post("/archive", summary="Archive log for a day")
async def archive_logs(
    body: ArchiveBody,
    mgr: LoggerManager = Depends(get_logger_mgr),
):
    result = mgr.archive_day(body.day, delete_source=body.delete_source)
    if result.get("ok"):
        mgr.info("router", f"Archived log file for {body.day}")
    else:
        mgr.warn("router", f"Failed to archive log file for {body.day}: {result.get('error', 'Unknown error')}")
    return result
