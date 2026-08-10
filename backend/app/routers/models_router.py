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

from ..gateway.providers.base import EndpointStatus, GatewayError, PROVIDER_SCHEMA


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



class ModelCreateBody(BaseModel):
    family: str
    provider: str
    model_path: Optional[str] = None
    model_name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    launch_cmd: Optional[List[str]] = None
    params: Optional[Dict] = None
    disabled: Optional[bool] = False


class ModelUpdateBody(BaseModel):
    provider: Optional[str] = None
    model_path: Optional[str] = None
    model_name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    launch_cmd: Optional[List[str]] = None
    params: Optional[Dict] = None
    disabled: Optional[bool] = None


def _get_manager(request: Request):
    return request.app.state.provider_manager


def _to_model_dict(endpoint, manager=None) -> Dict:
    spec = endpoint.spec
    disabled = False
    if manager is not None:
        providers = manager.get_config().get("providers", {})
        disabled = bool(providers.get(endpoint.name, {}).get("disabled", False))
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
        "disabled": disabled,
        "instance": endpoint.to_dict(),
    }


@router.get("", summary="List all configured model endpoints")
async def list_models(request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    models = [_to_model_dict(e, manager) for e in manager.list_endpoints()]
    return {"models": models}


@router.post("/scan", summary="Re-read provider config / rediscover endpoints")
async def scan_models(request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    manager.update_providers(manager.get_config().get("providers", {}))
    models = [_to_model_dict(e, manager) for e in manager.list_endpoints()]
    return {"models": models}


@router.get("/backends", summary="List available provider kinds and field schemas")
async def list_backends(request: Request):
    return {"backends": [
        {"kind": k, "label": k, "available": True, "schema": PROVIDER_SCHEMA.get(k, {})}
        for k in ("llamacpp", "vllm", "sglang")
    ]}


@router.get("/{family}", summary="Get model endpoint info")
async def get_model(family: str, request: Request):
    manager = _get_manager(request)
    endpoint = manager.get_endpoint(family)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Model not found")
    return _to_model_dict(endpoint, manager)


@router.get("/{family}/params", summary="Get sampling/launch params for an endpoint")
async def get_model_params(family: str, request: Request):
    manager = _get_manager(request)
    endpoint = manager.get_endpoint(family)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"family": family, "params": endpoint.spec.params}


class ParamsBody(BaseModel):
    params: Dict = {}


@router.put("/{family}/params", summary="Update launch/sampling params for an endpoint")
async def update_model_params(family: str, body: ParamsBody, request: Request,
                             _auth: None = auth_dep):
    """Update a provider's params in the gateway config (persisted to gateway.json)."""
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    if family not in providers:
        raise HTTPException(status_code=404, detail="Model not found")
    entry = dict(providers[family])
    entry["params"] = dict(body.params or {})
    providers[family] = entry
    manager.update_providers(providers)
    return {"ok": True, "family": family, "params": entry["params"]}


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




@router.post("", summary="Create a new model/provider configuration")
async def create_model(body: ModelCreateBody, request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    if body.family in providers:
        raise HTTPException(status_code=409, detail="Model already exists")
    if body.provider not in ("llamacpp", "vllm", "sglang"):
        raise HTTPException(status_code=400, detail="Invalid provider kind")
    default_host = manager.get_config().get("default_host", "127.0.0.1")
    entry = {
        "provider": body.provider,
        "host": body.host or default_host,
        "port": body.port or 8080,
        "params": body.params or {},
    }
    if body.model_path is not None:
        entry["model_path"] = body.model_path
    if body.model_name is not None:
        entry["model_name"] = body.model_name
    if body.launch_cmd is not None:
        entry["launch_cmd"] = body.launch_cmd
    if body.disabled:
        entry["disabled"] = True
    providers[body.family] = entry
    manager.update_providers(providers)
    return {"ok": True, "family": body.family, **entry}


@router.put("/{family}", summary="Update a model/provider configuration")
async def update_model(family: str, body: ModelUpdateBody, request: Request,
                       _auth: None = auth_dep):
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    if family not in providers:
        raise HTTPException(status_code=404, detail="Model not found")
    entry = dict(providers[family])
    if body.provider is not None:
        if body.provider not in ("llamacpp", "vllm", "sglang"):
            raise HTTPException(status_code=400, detail="Invalid provider kind")
        entry["provider"] = body.provider
    for f in ("model_path", "model_name", "host", "port", "launch_cmd"):
        val = getattr(body, f)
        if val is not None:
            entry[f] = val
    if body.params is not None:
        entry["params"] = body.params
    if body.disabled is not None:
        if body.disabled:
            entry["disabled"] = True
        else:
            entry.pop("disabled", None)
    providers[family] = entry
    manager.update_providers(providers)
    return {"ok": True, "family": family, "config": entry}


@router.delete("/{family}", summary="Delete a model/provider configuration")
async def delete_model(family: str, request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    if family not in providers:
        raise HTTPException(status_code=404, detail="Model not found")
    manager.remove_provider(family)
    return {"ok": True, "message": f"Model {family} deleted"}

@router.get("/{family}/status", summary="Get model status (disabled/enabled)")
async def get_model_status(family: str, request: Request, _auth: None = auth_dep):
    manager = _get_manager(request)
    providers = manager.get_config().get("providers", {})
    entry = providers.get(family, {})
    return {"family": family, "disabled": bool(entry.get("disabled", False))}
