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
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict

from ..main import get_config_mgr, get_model_registry, get_lifecycle_mgr
from ..plugins.model_registry import ModelRegistry
from ..plugins.lifecycle import PluginLifecycleManager


router = APIRouter()


class LoadModelBody(BaseModel):
    extra_args: Optional[List[str]] = None
    port: Optional[int] = None


@router.get("/")
async def list_models():
    registry = get_model_registry()
    return {"models": registry.list_models()}


@router.post("/scan")
async def scan_models():
    cfg = get_config_mgr().get_global()
    models_dir = cfg.get("models_dir", "")
    registry = get_model_registry()
    # Re-initialize with current models_dir
    new_registry = ModelRegistry(models_dir)
    # Update the global reference (hacky but works for MVP)
    import app.main as main_mod
    main_mod._model_registry = new_registry
    return {"models": new_registry.list_models()}


@router.get("/{family}")
async def get_model(family: str):
    registry = get_model_registry()
    info = registry.get_model(family)
    if not info:
        raise HTTPException(status_code=404, detail="Model not found")
    return registry._to_dict(info)


@router.get("/{family}/params")
async def get_model_params(family: str):
    registry = get_model_registry()
    params = registry.get_default_params(family)
    return {"family": family, "params": params}


@router.get("/backends")
async def list_backends():
    from ..plugins.backend_registry import list_all_available_backends
    cfg = get_config_mgr().get_global()
    results = list_all_available_backends(
        user_llama_dir=cfg.get("llama_backend_dir", ""),
        user_server_exe=cfg.get("llama_server_exe", ""),
    )
    return {"backends": [{
        "kind": b.kind, "label": b.label,
        "server_path": b.server_path, "available": b.available,
        "gpu_devices": b.gpu_devices, "root_dir": b.root_dir,
    } for b in results]}


@router.post("/{family}/load")
async def load_model(family: str, body: LoadModelBody = None):
    """Start llama-server with the specified model."""
    cfg = get_config_mgr().get_global()
    registry = get_model_registry()
    lifecycle = get_lifecycle_mgr()

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
    if body and body.extra_args:
        pass  # TODO: merge extra args
    port = body.port if body and body.port else cfg.get("default_port_range", [8080, 8099])[0]

    args = registry.build_server_args(family, params, backend.server_path)
    # Override port
    if "-p" in args or "--port" in args:
        pass  # TODO: replace existing port arg
    args = [args[0]] + ["--port", str(port)] + args[1:]

    inst = lifecycle.start_plugin(
        plugin_name=family,
        plugin_type="model",
        command=args,
        port=port,
    )
    return {"ok": True, "instance": inst.to_dict()}
