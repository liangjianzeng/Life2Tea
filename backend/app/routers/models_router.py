"""
models_router.py — Model Endpoint API (provider-based).

Exposes the gateway's configured providers/endpoints over /api/models so the
frontend Models/Providers view can list, load, unload and configure them.
No plugin-manifest concepts remain.
"""

import os
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict

from ..gateway.providers.base import EndpointStatus, GatewayError


async def verify_auth(request: Request):
    """Verify authentication - session cookie or API key."""
    session_id = request.cookies.get("life2tea_session")
    if session_id:
        try:
            from app.core.user_service import get_user_service
            user = get_user_service().validate_session(session_id)
            if user:
                request.state.current_user = user
                return
        except Exception:
            pass
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from app.core.api_keys import get_api_key_manager
            key = get_api_key_manager().verify_key(auth_header)
            if key:
                request.state.api_key = key
                return
        except Exception:
            pass
    # TEMPORARY: Skip authentication for testing (remove in production!)
    request.state.current_user = {"username": "admin", "role": "admin"}


auth_dep = Depends(verify_auth)

router = APIRouter()


class LoadModelBody(BaseModel):
    extra_args: Optional[List[str]] = None
    port: Optional[int] = None


def _get_manager(request: Request):
    return request.app.state.provider_manager


def _to_model_dict(endpoint) -> Dict:
    spec = endpoint.spec
    return {
        "family": endpoint.name,
        "display": endpoint.name,
        "provider": spec.kind.value,
        "host": endpoint.host,
        "port": endpoint.port,
        "model_path": spec.model_path,
        "model_name": spec.model_name,
        "status": endpoint.status.value,
        "pid": endpoint.pid,
        "params": spec.params,
        "instance": endpoint.to_dict(),
    }


@router.get("", summary="List all configured model endpoints")
async def list_models(request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    models = [_to_model_dict(e) for e in manager.list_endpoints()]
    return {"models": models}


@router.post("/scan", summary="Re-read provider config / rediscover endpoints")
async def scan_models(request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    manager.update_providers(manager.get_config().get("providers", {}))
    models = [_to_model_dict(e) for e in manager.list_endpoints()]
    return {"models": models}


@router.get("/{family}", summary="Get model endpoint info")
async def get_model(family: str, request: Request):
    manager = _get_manager(request)
    endpoint = manager.get_endpoint(family)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Model not found")
    return _to_model_dict(endpoint)


@router.get("/{family}/params", summary="Get sampling/launch params for an endpoint")
async def get_model_params(family: str, request: Request):
    manager = _get_manager(request)
    endpoint = manager.get_endpoint(family)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"family": family, "params": endpoint.spec.params}


@router.post("/{family}/load", summary="Start model backend")
async def load_model(family: str, request: Request, body: LoadModelBody = None,
                     _auth: None = auth_dep):
    manager = _get_manager(request)
    try:
        endpoint = await manager.start(family)
        return {"ok": True, "instance": endpoint.to_dict()}
    except GatewayError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{family}/unload", summary="Stop model backend")
async def unload_model(family: str, request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    try:
        endpoint = await manager.stop(family)
        return {"ok": True, "instance": endpoint.to_dict()}
    except GatewayError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/backends", summary="List available provider kinds")
async def list_backends(request: Request):
    manager = _get_manager(request)
    return {"backends": [
        {"kind": k, "label": k, "available": True}
        for k in ("llamacpp", "vllm", "sglang")
    ]}


@router.post("/{family}/disable", summary="Disable a model endpoint")
async def disable_model(family: str, request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    entry = providers.get(family, {})
    entry["disabled"] = True
    providers[family] = entry
    manager.update_providers(providers)
    return {"ok": True, "message": f"Model {family} disabled"}


@router.post("/{family}/enable", summary="Enable a model endpoint")
async def enable_model(family: str, request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    entry = providers.get(family, {})
    entry.pop("disabled", None)
    providers[family] = entry
    manager.update_providers(providers)
    return {"ok": True, "message": f"Model {family} enabled"}


@router.get("/{family}/status", summary="Get model status (disabled/enabled)")
async def get_model_status(family: str, request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    entry = providers.get(family, {})
    return {"family": family, "disabled": bool(entry.get("disabled", False))}
