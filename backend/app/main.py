"""
main.py — Life2Tea Backend API Server

FastAPI server providing the REST API for the Life2Tea desktop UI.
Modular router architecture — each resource group has its own router.

Architecture:
  UI (Electron/Tauri/Vue) → HTTP/SSE → FastAPI
                                  ├─ config_router    (global config, profiles)
                                  ├─ models_router    (model discovery, load/unload)
                                  ├─ plugins_router   (plugin registry, lifecycle)
                                  ├─ chat_router      (chat proxy, SSE stream)
                                  ├─ metrics_router   (performance stats)
                                  └─ logs_router      (log query, archive)
"""

import os
import sys
import json
import threading
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

# ── Load project root ──────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Core managers ──────────────────────────────────────
from app.core.config import ConfigManager
from app.core.logger import (
    LoggerManager, init_logger_manager, get_logger_manager
)
from app.core.metrics import MetricsCollector
from app.plugins.lifecycle import PluginLifecycleManager
from app.plugins.model_registry import ModelRegistry
from app.plugins.backend_registry import (
    detect_backend, list_all_available_backends, scan_system_for_llama_servers
)

# ── Routers (lazy import to avoid circular) ───────────
# Imported inside lifespan or route handlers to avoid circular imports


# ── Global state ───────────────────────────────────────
_config_mgr: Optional[ConfigManager] = None
_logger_mgr: Optional[LoggerManager] = None
_metrics_collector: Optional[MetricsCollector] = None
_lifecycle_mgr: Optional[PluginLifecycleManager] = None
_model_registry: Optional[ModelRegistry] = None

# Thread-safe lock for shared state
_state_lock = threading.RLock()


def _get_config_dir() -> str:
    return os.path.join(PROJECT_ROOT, "config")


def _get_log_dir() -> str:
    return os.path.join(PROJECT_ROOT, "log")


def _get_models_dir() -> str:
    cfg = _config_mgr.get_global() if _config_mgr else {}
    return cfg.get("models_dir", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    global _config_mgr, _logger_mgr, _metrics_collector
    global _lifecycle_mgr, _model_registry

    # ── Startup ────────────────────────────────────────
    config_dir = _get_config_dir()
    log_dir = _get_log_dir()
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    _config_mgr = ConfigManager(config_dir)
    init_logger_manager(log_dir, retention_days=30)
    _logger_mgr = get_logger_manager()
    _metrics_collector = MetricsCollector()
    _lifecycle_mgr = PluginLifecycleManager(log_dir)
    _model_registry = ModelRegistry(_get_models_dir())

    _logger_mgr.info("system", f"Life2Tea backend starting (project root: {PROJECT_ROOT})")
    _logger_mgr.info("system", f"Config dir: {config_dir}")
    _logger_mgr.info("system", f"Log dir: {log_dir}")

    # Auto-scan models if dir is configured
    models_dir = _get_models_dir()
    if models_dir and os.path.isdir(models_dir):
        _model_registry.scan()
        _logger_mgr.info("system", f"Scanned models dir: {models_dir}, found {len(_model_registry.list_models())} models")

    # ── Include routers after managers are initialized ──
    from app.routers import config_router, models_router, plugins_router
    from app.routers import chat_router, metrics_router, logs_router

    app.include_router(config_router.router, prefix="/api/config", tags=["Config"])
    app.include_router(models_router.router, prefix="/api/models", tags=["Models"])
    app.include_router(plugins_router.router, prefix="/api/plugins", tags=["Plugins"])
    app.include_router(chat_router.router, prefix="/api/chat", tags=["Chat"])
    app.include_router(metrics_router.router, prefix="/api/metrics", tags=["Metrics"])
    app.include_router(logs_router.router, prefix="/api/logs", tags=["Logs"])

    _logger_mgr.info("system", "Life2Tea backend started successfully")
    yield

    # ── Shutdown ───────────────────────────────────────
    if _logger_mgr:
        _logger_mgr.info("system", "Life2Tea backend shutting down")
    if _lifecycle_mgr:
        _lifecycle_mgr.stop_all()
    if _logger_mgr:
        _logger_mgr.info("system", "Life2Tea backend stopped")


# ── Create FastAPI app ─────────────────────────────────
app = FastAPI(
    title="Life2Tea API",
    description="Life2Tea — Local LLM Plugin Architecture Backend",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (allow Electron/Tauri localhost origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to localhost in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check (no router prefix) ───────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "project": "Life2Tea", "version": "0.1.0"}


# ── Root info ──────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "project": "Life2Tea",
        "version": "0.1.0",
        "description": "Local LLM Plugin Architecture",
        "routers": [
            "/api/config",
            "/api/models",
            "/api/plugins",
            "/api/chat",
            "/api/metrics",
            "/api/logs",
        ],
    }


# ── Expose managers to routers via module-level access ───
def get_config_mgr() -> ConfigManager:
    if _config_mgr is None:
        raise RuntimeError("ConfigManager not initialized")
    return _config_mgr


def get_logger_mgr() -> LoggerManager:
    if _logger_mgr is None:
        raise RuntimeError("LoggerManager not initialized")
    return _logger_mgr


def get_metrics_collector() -> MetricsCollector:
    if _metrics_collector is None:
        raise RuntimeError("MetricsCollector not initialized")
    return _metrics_collector


def get_lifecycle_mgr() -> PluginLifecycleManager:
    if _lifecycle_mgr is None:
        raise RuntimeError("PluginLifecycleManager not initialized")
    return _lifecycle_mgr


def get_model_registry() -> ModelRegistry:
    if _model_registry is None:
        raise RuntimeError("ModelRegistry not initialized")
    return _model_registry


# ── Server entry point ────────────────────────────────
def start_server(host: str = "127.0.0.1", port: int = 3001):
    """Start the FastAPI server (blocking)."""
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    cfg = _config_mgr.get_global() if _config_mgr else {}
    host = cfg.get("default_host", "127.0.0.1")
    port = int(os.environ.get("LIFE2TEA_PORT", 3001))
    start_server(host=host, port=port)
