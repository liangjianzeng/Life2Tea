"""
metrics_router.py — Performance Metrics API.

Endpoints:
  GET /api/metrics
  GET /api/metrics/{plugin_name}
  GET /api/metrics/recent
  GET /api/metrics/summary
  POST /api/metrics/reset
"""

from fastapi import APIRouter, Depends
from typing import List, Dict

from ..main import get_metrics_collector
from ..core.metrics import MetricsCollector


router = APIRouter()


@router.get("", summary="Get all plugin stats")
async def get_all_stats(collector: MetricsCollector = Depends(get_metrics_collector)):
    stats = collector.get_all_stats()
    collector.info("router", f"Requested plugin stats: {len(stats)} plugins")
    return {"stats": stats}


@router.get("/{plugin_name}", summary="Get stats for a specific plugin")
async def get_plugin_stats(
    plugin_name: str,
    collector: MetricsCollector = Depends(get_metrics_collector),
):
    return collector.get_plugin_stats(plugin_name)


@router.get("/recent", summary="Get recent inference records")
async def get_recent(
    limit: int = 20,
    collector: MetricsCollector = Depends(get_metrics_collector),
):
    return {"records": collector.get_recent_inferences(limit=limit)}


@router.get("/summary", summary="Get summary stats")
async def get_summary(collector: MetricsCollector = Depends(get_metrics_collector)):
    return collector.get_summary()


@router.post("/reset", summary="Reset all metrics")
async def reset_metrics(collector: MetricsCollector = Depends(get_metrics_collector)):
    collector.reset()
    return {"ok": True}
