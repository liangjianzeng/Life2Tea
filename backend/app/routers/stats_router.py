"""
stats_router.py — System Statistics API Endpoints

Provides endpoints for system monitoring, statistics, and logging.
"""

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from typing import Optional
from datetime import datetime

from ..core.stats_service import StatsService
from ..main import get_stats_service

router = APIRouter()


# ── Remote read-only auth ──────────────────────────────────
# Local UI (loopback) and valid session cookies are allowed without a key.
# Any other client (e.g. the Android monitor over VPN) must present a Bearer
# API key that carries the `read` scope. This keeps remote access read-only
# without breaking the local web UI.
async def require_read(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "::1"):
        return

    # Session cookie (web UI on the host machine)
    session_id = request.cookies.get("life2tea_session")
    if session_id:
        try:
            from app.core.user_service import get_user_service
            if get_user_service().validate_session(session_id):
                return
        except Exception:
            pass

    # Bearer API key with read scope (mobile/remote monitor)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.api_keys import get_api_key_manager, Scope
            key = get_api_key_manager().verify_key(auth_header)
            if key is not None and Scope.READ in key.scopes:
                request.state.api_key = key
                return
        except Exception:
            pass

    raise HTTPException(
        status_code=401,
        detail="Read-only API key required for remote access",
    )


# Alias so route signatures read naturally: `_auth: None = Depends(require_read)`
auth_read = Depends(require_read)


@router.get("/api/stats/dashboard")
async def get_dashboard_stats(
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get dashboard statistics"""
    return stats_service.get_dashboard_stats()


@router.get("/api/stats/system")
async def get_system_stats(
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get current system statistics"""
    return stats_service.get_system_metrics()


@router.get("/api/stats/resources")
async def get_resource_stats(
    range: str = Query("1h", description="Time range: 1h, 6h, 24h"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get resource usage statistics"""
    return stats_service.get_resource_usage(range)


@router.get("/api/stats/performance")
async def get_performance_stats(
    range: str = Query("1h", description="Time range: 1h, 6h, 24h"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get performance metrics"""
    return stats_service.get_performance_metrics(range)


@router.get("/api/stats/token-usage")
async def get_token_usage(
    range: str = Query("today", description="Time range: today, week, month"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get token usage statistics"""
    return stats_service.get_token_usage(range)


@router.get("/api/stats/model-metrics")
async def get_model_metrics(
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get model running metrics"""
    return stats_service.get_model_metrics()


@router.get("/api/stats/api-keys")
async def get_api_key_stats(
    key_id: Optional[int] = Query(None, description="Filter by API key ID"),
    range: str = Query("today", description="Time range: today, week, month"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get API key usage statistics"""
    return stats_service.get_api_key_stats(key_id, range)


@router.get("/api/stats/requests")
async def get_request_stats(
    limit: int = Query(50, ge=1, le=1000, description="Number of recent requests"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get recent request statistics"""
    return stats_service.get_recent_requests(limit)


@router.get("/api/stats/recent-logs")
async def get_recent_logs(
    level: Optional[str] = Query(None, description="Log level: info, warning, error, debug"),
    limit: int = Query(50, ge=1, le=200, description="Number of logs to return"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get recent system logs"""
    return stats_service.get_logs(level=level, limit=limit)


@router.get("/api/stats/key-detail")
async def get_api_key_detail(
    key_id: Optional[str] = Query(None, description="API key ID"),
    limit: int = Query(50, ge=1, le=500, description="Number of requests"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Get detailed request history for an API key"""
    return stats_service.get_api_key_detail(key_id, limit)


@router.get("/api/stats/gateway/summary")
async def get_gateway_usage_summary(
    period: str = Query("month", description="day, week, month, all"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Per-model request / token / tps summary for a period (day, week, month)."""
    return stats_service.get_gateway_summary(period)


@router.get("/api/stats/gateway/series")
async def get_gateway_usage_series(
    period: str = Query("month", description="day, week, month, all"),
    granularity: str = Query("day", description="hour, day, month"),
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Time-series buckets of requests / tokens."""
    return stats_service.get_gateway_series(period, granularity)


@router.get("/api/stats/gateway/compare")
async def get_gateway_usage_compare(
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    """Compare current vs previous month / week."""
    return stats_service.get_gateway_period_compare()


# ── Mobile aggregate endpoint ──────────────────────────────
# One call returns everything the Android dashboard needs, so the phone makes a
# single round-trip per refresh (friendly on mobile networks).
@router.get("/api/mobile/dashboard", summary="Mobile aggregate dashboard")
async def get_mobile_dashboard(
    request: Request,
    stats_service: StatsService = Depends(get_stats_service),
    _auth: None = auth_read,
):
    from ..gateway.providers.base import EndpointStatus
    from datetime import datetime as _dt

    gateway = getattr(request.app.state, "gateway", None)
    providers_count = 0
    running = []
    if gateway is not None:
        endpoints = gateway.manager.list_endpoints()
        providers_count = len(endpoints)
        running = [
            e.name for e in endpoints if e.status == EndpointStatus.RUNNING
        ]

    return {
        "updated_at": _dt.now().isoformat(),
        "system": stats_service.collect_system_metrics(),
        "model_metrics": stats_service.get_model_metrics(),
        "gateway": {
            "providers": providers_count,
            "running": running,
        },
        "gateway_summary": stats_service.get_gateway_summary("day"),
        "series": stats_service.get_gateway_series("day", "hour"),
    }
