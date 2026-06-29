"""
stats_middleware.py — System Statistics Middleware

Collects request statistics for monitoring and analytics.
Uses lazy import to avoid circular dependencies and initialization order issues.
"""

import asyncio
import time
from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Lazy import to avoid circular import at module level
_stats_service = None
_last_record_time = 0.0
_RECORD_INTERVAL = 60  # seconds between system metrics snapshots


def _get_stats_service():
    """Get StatsService instance lazily."""
    global _stats_service
    if _stats_service is None:
        from ..core.stats_service import StatsService
        # Try to get from app.state
        try:
            from ..main import app as _app
            _stats_service = _app.state.stats_service
        except Exception:
            pass
    return _stats_service


def register_stats_service(service):
    """Register the StatsService instance (called during startup)."""
    global _stats_service
    _stats_service = service


class StatsMiddleware(BaseHTTPMiddleware):
    """System statistics middleware"""

    async def dispatch(self, request: Request, call_next):
        global _last_record_time

        print(f"*** StatsMiddleware DISPATCH CALLED *** {request.method} {request.url.path}", flush=True)

        start_time = time.time()

        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Process request
        response = await call_next(request)

        response_time = time.time() - start_time
        status_code = response.status_code

        # Record request (fire-and-forget)
        svc = _get_stats_service()
        if svc is not None:
            try:
                svc.record_request(
                    method=method,
                    path=path,
                    status_code=status_code,
                    response_time=response_time,
                    client_ip=client_ip,
                    timestamp=datetime.now().isoformat(),
                )
            except Exception:
                pass

            # Periodically record system metrics (CPU, memory, GPU, etc.)
            now = time.time()
            if now - _last_record_time >= _RECORD_INTERVAL:
                _last_record_time = now
                try:
                    metrics = svc.collect_system_metrics()
                    svc._record_system_metrics(metrics)
                except Exception:
                    pass

        return response
