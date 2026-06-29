"""
stats_router.py — System Statistics API Endpoints

Provides endpoints for system monitoring, statistics, and logging.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime

from ..core.stats_service import StatsService
from ..main import get_stats_service

router = APIRouter()


@router.get("/api/stats/dashboard")
async def get_dashboard_stats(
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get dashboard statistics"""
    return stats_service.get_dashboard_stats()


@router.get("/api/stats/system")
async def get_system_stats(
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get current system statistics"""
    return stats_service.get_system_metrics()


@router.get("/api/stats/resources")
async def get_resource_stats(
    range: str = Query("1h", description="Time range: 1h, 6h, 24h"),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get resource usage statistics"""
    return stats_service.get_resource_usage(range)


@router.get("/api/stats/performance")
async def get_performance_stats(
    range: str = Query("1h", description="Time range: 1h, 6h, 24h"),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get performance metrics"""
    return stats_service.get_performance_metrics(range)


@router.get("/api/stats/token-usage")
async def get_token_usage(
    range: str = Query("today", description="Time range: today, week, month"),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get token usage statistics"""
    return stats_service.get_token_usage(range)


@router.get("/api/stats/model-metrics")
async def get_model_metrics(
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get model running metrics"""
    return stats_service.get_model_metrics()


@router.get("/api/stats/api-keys")
async def get_api_key_stats(
    key_id: Optional[int] = Query(None, description="Filter by API key ID"),
    range: str = Query("today", description="Time range: today, week, month"),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get API key usage statistics"""
    return stats_service.get_api_key_stats(key_id, range)


@router.get("/api/stats/requests")
async def get_request_stats(
    limit: int = Query(50, ge=1, le=1000, description="Number of recent requests"),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get recent request statistics"""
    return stats_service.get_recent_requests(limit)


@router.get("/api/stats/recent-logs")
async def get_recent_logs(
    level: Optional[str] = Query(None, description="Log level: info, warning, error, debug"),
    limit: int = Query(50, ge=1, le=200, description="Number of logs to return"),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get recent system logs"""
    return stats_service.get_logs(level=level, limit=limit)


@router.get("/api/stats/key-detail")
async def get_api_key_detail(
    key_id: Optional[str] = Query(None, description="API key ID"),
    limit: int = Query(50, ge=1, le=500, description="Number of requests"),
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get detailed request history for an API key"""
    return stats_service.get_api_key_detail(key_id, limit)


@router.get("/api/stats/token-usage")
async def get_token_usage(
    stats_service: StatsService = Depends(get_stats_service)
):
    """Get token usage statistics (placeholder)"""
    return stats_service.get_token_usage()
