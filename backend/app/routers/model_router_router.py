"""
model_router_router.py — Unified Model Router API Endpoints

Provides endpoints for:
- Listing available model instances
- Routing requests to models
- Managing model instances
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List

from ..main import get_model_router, get_config_mgr
from ..core.model_router import ModelRouter, LoadBalanceStrategy
from ..core.stats_service import StatsService


router = APIRouter()


class RouteRequest(BaseModel):
    model_name: Optional[str] = None
    strategy: str = "idle"  # idle, round_robin, priority


class RouteResponse(BaseModel):
    success: bool
    model_family: Optional[str] = None
    port: Optional[int] = None
    host: str = "127.0.0.1"
    message: Optional[str] = None


class InstanceInfo(BaseModel):
    family: str
    port: int
    host: str
    status: str
    last_used: float
    request_count: int


@router.get("/instances", summary="List all running model instances")
async def list_instances(
    request: Request,
    router: ModelRouter = Depends(get_model_router),
    _auth: None = None,  # Optional auth
):
    """List all currently running model instances."""
    instances = router.list_instances()
    return {
        "instances": [
            {
                "family": i.family,
                "port": i.port,
                "host": i.host,
                "status": i.status,
                "last_used": i.last_used,
            }
            for i in instances
        ]
    }


@router.post("/route", summary="Route request to appropriate model")
async def route_request(
    request: Request,
    body: RouteRequest,
    router: ModelRouter = Depends(get_model_router),
):
    """
    Route a request to an appropriate model instance.
    
    - If model_name is provided, route to that specific model
    - Otherwise, use load balancing strategy to pick idle model
    """
    try:
        strategy = LoadBalanceStrategy(body.strategy.lower())
    except ValueError:
        strategy = LoadBalanceStrategy.IDLE
    
    instance = router.route_request(
        model_name=body.model_name,
        strategy=strategy,
    )
    
    if instance:
        return RouteResponse(
            success=True,
            model_family=instance.family,
            port=instance.port,
            host=instance.host,
        )
    else:
        return RouteResponse(
            success=False,
            message="No model instance available",
        )


@router.get("/common-models", summary="Get list of common models")
async def get_common_models(
    request: Request,
    router: ModelRouter = Depends(get_model_router),
):
    """Get list of common models that are exposed on unified endpoint."""
    return {"models": router.get_common_models()}


@router.get("/status", summary="Get router status")
async def get_status(
    request: Request,
    router: ModelRouter = Depends(get_model_router),
):
    """Get router status and statistics."""
    instances = router.list_instances()
    return {
        "instance_count": len(instances),
        "common_models": router.get_common_models(),
        "instances": [
            {
                "family": i.family,
                "port": i.port,
                "status": i.status,
            }
            for i in instances
        ],
    }


@router.post("/{family}/deregister", summary="Deregister a model instance")
async def deregister_instance(
    family: str,
    request: Request,
    router: ModelRouter = Depends(get_model_router),
    _auth: None = None,  # Optional auth
):
    """Deregister a model instance (mark as stopped)."""
    instance = router.get_instance(family)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {family} not found")
    
    router.unregister_instance(family)
    return {"ok": True, "message": f"Instance {family} deregistered"}
