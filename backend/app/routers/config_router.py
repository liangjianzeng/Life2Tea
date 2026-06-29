"""
config_router.py — Configuration & Profiles API.

Endpoints:
  GET  /api/config/global
  POST /api/config/global
  GET  /api/config/profiles
  POST /api/config/profiles
  DELETE /api/config/profiles/{name}
  GET  /api/config/model/{family}
  POST /api/config/model/{family}
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict

from ..main import get_config_mgr
from ..core.config import ConfigManager


router = APIRouter()


class ProfileBody(BaseModel):
    name: str
    params: Dict
    description: str = ""


class ModelConfigBody(BaseModel):
    params: Dict


@router.get("/global")
async def get_global_config(mgr: ConfigManager = Depends(get_config_mgr)):
    return mgr.get_global()


@router.post("/global")
async def save_global_config(body: Dict, mgr: ConfigManager = Depends(get_config_mgr)):
    mgr.save_global(body)
    return {"ok": True}


@router.get("/profiles")
async def list_profiles(mgr: ConfigManager = Depends(get_config_mgr)):
    return mgr.list_profiles()


@router.post("/profiles")
async def save_profile(body: ProfileBody, mgr: ConfigManager = Depends(get_config_mgr)):
    mgr.save_profile(body.name, body.params, description=body.description)
    return {"ok": True}


@router.delete("/profiles/{name}")
async def delete_profile(name: str, mgr: ConfigManager = Depends(get_config_mgr)):
    ok = mgr.delete_profile(name)
    return {"ok": ok}


@router.get("/model/{family}")
async def get_model_config(family: str, mgr: ConfigManager = Depends(get_config_mgr)):
    data = mgr.get_plugin_config(family)  # use plugin key
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return data


@router.post("/model/{family}")
async def save_model_config(family: str, body: ModelConfigBody, mgr: ConfigManager = Depends(get_config_mgr)):
    mgr.save_plugin_config(family, body.params)
    return {"ok": True}


# ── Model-Specific Configuration API ──────────────────────────────────

@router.get("/model-configs")
async def list_model_configs(mgr: ConfigManager = Depends(get_config_mgr)):
    """List all model-specific configurations."""
    return mgr.list_model_configs()


@router.get("/model-config/{model}")
async def get_model_specific_config(model: str, mgr: ConfigManager = Depends(get_config_mgr)):
    """Get configuration for a specific model."""
    config = mgr.get_model_config(model)
    if config is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    return config


@router.post("/model-config/{model}")
async def save_model_specific_config(model: str, body: ModelConfigBody, mgr: ConfigManager = Depends(get_config_mgr)):
    """Save configuration for a specific model."""
    mgr.save_model_config(model, body.params)
    return {"ok": True}


@router.delete("/model-config/{model}")
async def delete_model_specific_config(model: str, mgr: ConfigManager = Depends(get_config_mgr)):
    """Delete configuration for a specific model."""
    ok = mgr.delete_model_config(model)
    if not ok:
        raise HTTPException(status_code=404, detail="Model config not found")
    return {"ok": True}


# ── Directory browsing API ────────────────────────────────────────────

def _safe_path(raw_path: str) -> Optional[str]:
    """Validate and normalize a user-supplied path.

    Returns the absolute normalized path if safe, otherwise None.
    Disallows path traversal (..), requires the path to exist.
    """
    import platform

    if not raw_path or not isinstance(raw_path, str):
        return None

    # Normalize separators and resolve
    normalized = os.path.normpath(raw_path)

    # Block path traversal
    if ".." in normalized.split(os.sep):
        return None

    # On Windows, require a valid drive letter
    if platform.system() == "Windows":
        if len(normalized) < 2 or normalized[1] != ":":
            return None

    # Must exist on disk
    if not os.path.exists(normalized):
        return None

    return normalized


@router.get("/dirs/list")
async def list_directory(path: str):
    """List contents of a directory (subdirs + files)."""
    safe = _safe_path(path)
    if safe is None:
        raise HTTPException(status_code=400, detail="Invalid or inaccessible path")

    if not os.path.isdir(safe):
        raise HTTPException(status_code=400, detail="Not a directory")

    try:
        entries = os.listdir(safe)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied")

    dirs = []
    files = []
    for name in sorted(entries):
        full = os.path.join(safe, name)
        if os.path.isdir(full):
            # Only include directories with at least one entry (to avoid listing deep trees)
            try:
                sub = os.listdir(full)
                if sub:
                    dirs.append(name)
            except PermissionError:
                dirs.append(name)
        else:
            files.append(name)

    return {"path": safe, "dirs": dirs, "files": files}


@router.get("/dirs/exists")
async def check_directory(path: str):
    """Check if a path exists and whether it is a directory or file."""
    safe = _safe_path(path)
    if safe is None:
        return {"exists": False}

    is_dir = os.path.isdir(safe)
    return {"exists": True, "is_dir": is_dir, "path": safe}
