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

from ..main import get_config_mgr, get_model_registry, get_lifecycle_mgr, get_plugin_registry
from ..plugins.model_registry import ModelRegistry
from ..plugins.lifecycle import PluginLifecycleManager
from ..plugins.registry import ModelInfoAdapter
from ..core.config import ConfigManager


router = APIRouter()


class LoadModelBody(BaseModel):
    extra_args: Optional[List[str]] = None
    port: Optional[int] = None


def _merge_plugin_models(legacy_models: List[Dict], plugin_registry) -> List[Dict]:
    """Add model-type plugins not already present (by family) in the legacy list.

    Plugin-backed models carry ``source: "plugin"`` so the frontend can tell
    them apart from raw GGUFs (``source`` defaults to absent/"gguf").
    """
    if plugin_registry is None:
        return legacy_models
    seen = {m.get("family") for m in legacy_models}
    out = list(legacy_models)
    for desc in plugin_registry.list_plugins(type="model"):
        if desc.errors:
            continue
        if desc.manifest.model and desc.manifest.model.model_family not in seen:
            try:
                out.append(ModelInfoAdapter.from_manifest(desc.manifest).to_dict())
            except Exception:
                continue
    return out


@router.get("", summary="List all discovered models (GGUFs + plugins)")
async def list_models(
    registry: ModelRegistry = Depends(get_model_registry),
    plugin_registry=Depends(get_plugin_registry),
):
    models = _merge_plugin_models(registry.list_models(), plugin_registry)
    return {"models": models}


@router.post("/scan", summary="Re-scan models directory")
async def scan_models(
    cfg_mgr: ConfigManager = Depends(get_config_mgr),
    registry: ModelRegistry = Depends(get_model_registry),
    plugin_registry=Depends(get_plugin_registry),
):
    cfg = cfg_mgr.get_global()
    models_dir = cfg.get("models_dir", "")
    new_registry = ModelRegistry(models_dir)
    # Update app.state so future requests see the new registry
    import app.main as main_mod
    main_mod.app.state.model_registry = new_registry
    # Refresh the plugin registry too (new GGUFs become fallback descriptors)
    if plugin_registry is not None:
        plugin_registry.env["MODELS_DIR"] = models_dir
        plugin_registry.discover_with_gguf_fallback(models_dir)
        main_mod.app.state.plugin_registry = plugin_registry
    models = _merge_plugin_models(new_registry.list_models(), plugin_registry)
    return {"models": models}


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
    """Start llama-server with the specified model (fully automated)."""
    print(f"[load_model] ENTRY: family={family}, body={body}", flush=True)
    cfg = cfg_mgr.get_global()
    info = registry.get_model(family)
    if not info:
        raise HTTPException(status_code=404, detail="Model not found")

    # Determine port
    port = body.port if body and body.port else cfg.get("default_port_range", [8080, 8099])[0]

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
    params["ngl"] = cfg.get("gpu_layers", params["ngl"])
    params["ctx"] = cfg.get("ctx_size", params.get("ctx", 32768))
    args = registry.build_server_args(family, params, backend.server_path)

    # Check if already running
    try:
        import subprocess, psutil
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.split("\n"):
            if "LISTENING" in line.upper() and f":{port} " in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid_running = parts[-1].strip()
                    try:
                        proc = psutil.Process(int(pid_running))
                        if "llama-server" in proc.name().lower():
                            from ..plugins.lifecycle import PluginStatus, PluginInstance
                            inst = lifecycle.get_instance(family)
                            if not inst:
                                inst = PluginInstance(
                                    plugin_name=family,
                                    plugin_type="model",
                                    pid=int(pid_running),
                                    process=None,
                                    port=port,
                                    status=PluginStatus.RUNNING,
                                    health_endpoint="/health",
                                )
                                lifecycle._instances[family] = inst
                            return {"ok": True, "instance": inst.to_dict(), "note": "Already running (port in use)"}
                    except Exception:
                        pass
    except Exception as e:
        print(f"[load_model] Error checking process: {e}", flush=True)

    # Not running — start it automatically using lifecycle manager
    print(f"[load_model] Starting model on port {port}", flush=True)
    try:
        instance = lifecycle.start_plugin(
            plugin_name=family,
            plugin_type="model",
            command=args,
            host=cfg.get("default_host", "127.0.0.1"),
            port=port,
            health_endpoint="/health",
        )
        return {"ok": True, "instance": instance.to_dict()}
    except Exception as e:
        print(f"[load_model] Failed to start: {e}", flush=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start model: {e}",
        )
