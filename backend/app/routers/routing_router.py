"""
routing_router.py — Router Rules API (gateway-backed).

Endpoints:
  GET    /api/router/rules       — Get current routing rules
  PUT    /api/router/rules       — Update routing rules
  POST   /api/router/predict     — Predict which model for a request
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter()


def _get_gateway(request: Request):
    """Get the shared gateway (manager + router) from app.state."""
    return request.app.state.gateway


class RoutingRulesUpdate(BaseModel):
    rules: Dict[str, List[str]]


class PredictRequest(BaseModel):
    messages: List[Dict[str, str]]
    model_preference: Optional[str] = None


@router.get("/rules", summary="Get current routing rules")
async def get_rules(request: Request):
    gateway = _get_gateway(request)
    return {"rules": gateway.router.get_rules()}


@router.put("/rules", summary="Update routing rules")
async def update_rules(body: RoutingRulesUpdate, request: Request):
    gateway = _get_gateway(request)
    gateway.router.update_rules(body.rules)
    return {"status": "ok", "rules": gateway.router.get_rules()}


@router.post("/predict", summary="Predict which model for a request")
async def predict_model(body: PredictRequest, request: Request):
    """Predict the fallback chain for a request."""
    gateway = _get_gateway(request)
    task_type = gateway.router.classify_task(body.messages)
    chain = gateway.router.route_chain(body.messages, body.model_preference)
    return {
        "task_type": task_type,
        "candidates": [e.name for e in chain],
        "selected": chain[0].name if chain else None,
    }
