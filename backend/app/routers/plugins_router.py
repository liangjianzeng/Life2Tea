"""
plugins_router.py — Plugin Lifecycle API.

Endpoints:
  GET  /api/plugins
  GET  /api/plugins/{name}
  POST /api/plugins/{name}/load
  POST /api/plugins/{name}/unload
  GET  /api/plugins/{name}/health
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict

from ..main import get_lifecycle_mgr, get_model_registry, get_config_mgr
from ..plugins.lifecycle import PluginLifecycleManager
from ..plugins.model_registry import ModelRegistry
from ..core.config import ConfigManager


router = APIRouter()


class LoadPluginBody(BaseModel):
    command: Optional[List[str]] = None
    host: str = "127.0.0.1"
    port: int = 0
    health_endpoint: str = "/health"
    env: Optional[Dict[str, str]] = None


@router.get("", summary="List all plugins and running instances")
async def list_plugins(
    registry: ModelRegistry = Depends(get_model_registry),
    lifecycle: PluginLifecycleManager = Depends(get_lifecycle_mgr),
):
    models = registry.list_models()
    instances = lifecycle.list_instances()
    instance_map = {i["plugin_name"]: i for i in instances}
    result = []
    for m in models:
        entry = dict(m)
        entry["instance"] = instance_map.get(m["family"], None)
        result.append(entry)
    return {"plugins": result, "running": instances}


@router.get("/{name}", summary="Get plugin info and instance status")
async def get_plugin(
    name: str,
    registry: ModelRegistry = Depends(get_model_registry),
    lifecycle: PluginLifecycleManager = Depends(get_lifecycle_mgr),
):
    info = registry.get_model(name)
    if not info:
        raise HTTPException(status_code=404, detail="Plugin not found")
    inst = lifecycle.get_instance(name)
    return {"plugin": info, "instance": inst.to_dict() if inst else None}


@router.post("/{name}/load", summary="Start a plugin instance")
async def load_plugin(
    name: str,
    body: LoadPluginBody = None,
    cfg_mgr: ConfigManager = Depends(get_config_mgr),
    registry: ModelRegistry = Depends(get_model_registry),
    lifecycle: PluginLifecycleManager = Depends(get_lifecycle_mgr),
):
    info = registry.get_model(name)
    if not info:
        raise HTTPException(status_code=404, detail="Model not found")

    if body and body.command:
        command = body.command
        port = body.port or cfg_mgr.get_global().get("default_port_range", [8080, 8099])[0]
        inst = lifecycle.start_plugin(
            plugin_name=name,
            plugin_type="model",
            command=command,
            host=body.host,
            port=port,
            health_endpoint=body.health_endpoint,
            env=body.env,
        )
    else:
        raise HTTPException(status_code=400, detail="command required")

    return {"ok": True, "instance": inst.to_dict()}


@router.post("/{name}/unload", summary="Stop a plugin instance")
async def unload_plugin(
    name: str,
    lifecycle: PluginLifecycleManager = Depends(get_lifecycle_mgr),
):
    ok = lifecycle.stop_plugin(name)
    return {"ok": ok}


@router.get("/{name}/health", summary="Check plugin health")
async def check_plugin_health(
    name: str,
    lifecycle: PluginLifecycleManager = Depends(get_lifecycle_mgr),
):
    return lifecycle.check_health(name)
