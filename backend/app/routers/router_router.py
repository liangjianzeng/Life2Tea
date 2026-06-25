"""
router_router.py — Router Rules API.

Endpoints:
  GET    /api/router/rules       — Get current routing rules
  PUT    /api/router/rules       — Update routing rules
  POST   /api/router/predict     — Predict which model for a request
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from ..core.router import SystemRouter

router = APIRouter()


def _get_router(request: Request) -> SystemRouter:
    """Get SystemRouter instance from app.state."""
    return request.app.state.system_router


class RoutingRulesUpdate(BaseModel):
    rules: Dict[str, List[str]]


class PredictRequest(BaseModel):
    messages: List[Dict[str, str]]
    model_preference: Optional[str] = None


@router.get("/rules", summary="Get current routing rules")
async def get_rules(request: Request):
    router = _get_router(request)
    return {"rules": router.get_rules()}


@router.put("/rules", summary="Update routing rules")
async def update_rules(body: RoutingRulesUpdate, request: Request):
    router = _get_router(request)
    router.update_rules(body.rules)
    return {"status": "ok", "rules": router.get_rules()}


@router.post("/predict", summary="Predict which model for a request")
async def predict_model(body: PredictRequest, request: Request):
    """Predict which model plugin would be selected for this request."""
    router = _get_router(request)
    task_type = router.classify_task(body.messages)
    candidates = router.rules.get(task_type, router.rules["default"])

    return {
        "task_type": task_type,
        "candidates": candidates,
        "selected": candidates[0] if candidates else None,
    }
