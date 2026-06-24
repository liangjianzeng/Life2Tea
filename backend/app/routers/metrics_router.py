"""
metrics_router.py — Performance Metrics API.

Endpoints:
  GET /api/metrics
  GET /api/metrics/{plugin_name}
  GET /api/metrics/recent
  GET /api/metrics/summary
  POST /api/metrics/reset
"""

from fastapi import APIRouter
from typing import List, Dict

from ..main import get_metrics_collector


router = APIRouter()


@router.get("/")
async def get_all_stats():
    collector = get_metrics_collector()
    return {"stats": collector.get_all_stats()}


@router.get("/{plugin_name}")
async def get_plugin_stats(plugin_name: str):
    collector = get_metrics_collector()
    return collector.get_plugin_stats(plugin_name)


@router.get("/recent")
async def get_recent(limit: int = 20):
    collector = get_metrics_collector()
    return {"records": collector.get_recent_inferences(limit=limit)}


@router.get("/summary")
async def get_summary():
    collector = get_metrics_collector()
    return collector.get_summary()


@router.post("/reset")
async def reset_metrics():
    collector = get_metrics_collector()
    collector.reset()
    return {"ok": True}
