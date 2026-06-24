"""
models_router.py — Model Discovery & Lifecycle API.

Endpoints:
  GET  /api/models
  GET  /api/models/scan
  GET  /api/models/{family}
  POST /api/models/{family}/load
  POST /api/models/{family}/unload
  GET  /api/models/{family}/params
  GET  /api/models/backends
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict

from ..main import get_config_mgr, get_model_registry, get_lifecycle_mgr
from ..plugins.model_registry import ModelRegistry
from ..plugins.lifecycle import PluginLifecycleManager
from ..core.config import ConfigManager


router = APIRouter()


class LoadModelBody(BaseModel):
    extra_args: Optional[List[str]] = None
    port: Optional[int] = None


@router.get("", summary="List all discovered models")
async def list_models(registry: ModelRegistry = Depends(get_model_registry)):
    return {"models": registry.list_models()}


@router.post("/scan", summary="Re-scan models directory")
async def scan_models(
    cfg_mgr: ConfigManager = Depends(get_config_mgr),
    registry: ModelRegistry = Depends(get_model_registry),
):
    cfg = cfg_mgr.get_global()
    models_dir = cfg.get("models_dir", "")
    new_registry = ModelRegistry(models_dir)
    # Update app.state so future requests see the new registry
    from fastapi import Request
    import app.main as main_mod
    main_mod.app.state.model_registry = new_registry
    return {"models": new_registry.list_models()}


@router.get("/{family}", summary="Get model info")
async def get_model(
    family: str,
    registry: ModelRegistry = Depends(get_model_registry),
):
    info = registry.get_model(family)
    if not info:
        raise HTTPException(status_code=404, detail="Model not found")
    return registry._to_dict(info)


@router.get("/{family}/params", summary="Get default params for a model family")
async def get_model_params(
    family: str,
    registry: ModelRegistry = Depends(get_model_registry),
):
    params = registry.get_default_params(family)
    return {"family": family, "params": params}


@router.get("/backends", summary="List available LLM backends")
async def list_backends(cfg_mgr: ConfigManager = Depends(get_config_mgr)):
    from ..plugins.backend_registry import list_all_available_backends
    cfg = cfg_mgr.get_global()
    results = list_all_available_backends(
        user_llama_dir=cfg.get("llama_backend_dir", ""),
        user_server_exe=cfg.get("llama_server_exe", ""),
    )
    return {"backends": [{
        "kind": b.kind, "label": b.label,
        "server_path": b.server_path, "available": b.available,
        "gpu_devices": b.gpu_devices, "root_dir": b.root_dir,
    } for b in results]}


@router.post("/{family}/load", summary="Start LLM backend with this model")
async def load_model(
    family: str,
    body: LoadModelBody = None,
    cfg_mgr: ConfigManager = Depends(get_config_mgr),
    registry: ModelRegistry = Depends(get_model_registry),
    lifecycle: PluginLifecycleManager = Depends(get_lifecycle_mgr),
):
    """Start llama-server with the specified model."""
    cfg = cfg_mgr.get_global()
    info = registry.get_model(family)
    if not info:
        raise HTTPException(status_code=404, detail="Model not found")

    # Find backend
    from ..plugins.backend_registry import detect_backend
    backend = detect_backend(
        user_llama_dir=cfg.get("llama_backend_dir", ""),
        user_server_exe=cfg.get("llama_server_exe", ""),
        preference=cfg.get("backend_preference", "auto"),
    )
    if not backend.available or not backend.server_path:
        raise HTTPException(status_code=500, detail="No backend available")

    # Build command
    params = registry.get_default_params(family)
    port = body.port if body and body.port else cfg.get("default_port_range", [8080, 8099])[0]

    args = registry.build_server_args(family, params, backend.server_path)
    # Prepend --port
    args = [args[0]] + ["--port", str(port)] + args[1:]

    inst = lifecycle.start_plugin(
        plugin_name=family,
        plugin_type="model",
        command=args,
        port=port,
    )
    return {"ok": True, "instance": inst.to_dict()}
