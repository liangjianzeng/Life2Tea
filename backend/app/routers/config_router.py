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
from fastapi import APIRouter, HTTPException
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
async def get_global_config():
    mgr = get_config_mgr()
    return mgr.get_global()


@router.post("/global")
async def save_global_config(body: Dict):
    mgr = get_config_mgr()
    mgr.save_global(body)
    return {"ok": True}


@router.get("/profiles")
async def list_profiles():
    mgr = get_config_mgr()
    return mgr.list_profiles()


@router.post("/profiles")
async def save_profile(body: ProfileBody):
    mgr = get_config_mgr()
    mgr.save_profile(body.name, body.params, description=body.description)
    return {"ok": True}


@router.delete("/profiles/{name}")
async def delete_profile(name: str):
    mgr = get_config_mgr()
    ok = mgr.delete_profile(name)
    return {"ok": ok}


@router.get("/model/{family}")
async def get_model_config(family: str):
    mgr = get_config_mgr()
    data = mgr.get_plugin_config(family)  # use plugin key
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    return data


@router.post("/model/{family}")
async def save_model_config(family: str, body: ModelConfigBody):
    mgr = get_config_mgr()
    mgr.save_plugin_config(family, body.params)
    return {"ok": True}
