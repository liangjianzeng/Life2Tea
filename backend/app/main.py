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
# __file__ = backend/app/main.py → PROJECT_ROOT = 3 levels up
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

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


# ── Helpers to get managers from app.state ───────────
def _get_state(request: Request = None):
    """Get the FastAPI app instance and its state."""
    if request is not None:
        return request.app.state
    # Fallback: access app via the module-level `app` object
    from app.main import app
    return app.state


def get_config_mgr(request: Request = None) -> ConfigManager:
    state = _get_state(request)
    mgr = getattr(state, "config_mgr", None)
    if mgr is None:
        raise RuntimeError("ConfigManager not initialized")
    return mgr


def get_logger_mgr(request: Request = None) -> LoggerManager:
    state = _get_state(request)
    mgr = getattr(state, "logger_mgr", None)
    if mgr is None:
        raise RuntimeError("LoggerManager not initialized")
    return mgr


def get_metrics_collector(request: Request = None) -> MetricsCollector:
    state = _get_state(request)
    mgr = getattr(state, "metrics_collector", None)
    if mgr is None:
        raise RuntimeError("MetricsCollector not initialized")
    return mgr


def get_lifecycle_mgr(request: Request = None) -> PluginLifecycleManager:
    state = _get_state(request)
    mgr = getattr(state, "lifecycle_mgr", None)
    if mgr is None:
        raise RuntimeError("PluginLifecycleManager not initialized")
    return mgr


def get_model_registry(request: Request = None) -> ModelRegistry:
    state = _get_state(request)
    mgr = getattr(state, "model_registry", None)
    if mgr is None:
        raise RuntimeError("ModelRegistry not initialized")
    return mgr


def get_plugin_registry(request: Request = None):
    """PluginRegistry dependency. Returns None if not initialized (e.g. in
    unit tests) so routers can degrade gracefully to the legacy registry."""
    state = _get_state(request)
    return getattr(state, "plugin_registry", None)


def _get_config_dir() -> str:
    return os.path.join(PROJECT_ROOT, "config")


def _get_log_dir() -> str:
    return os.path.join(PROJECT_ROOT, "log")


def _get_models_dir() -> str:
    # Can't use get_config_mgr here because this is called during startup
    # before the state is fully initialized. Read config file directly.
    # life2tea.json is the single source of truth for global config.
    config_dir = _get_config_dir()
    config_path = os.path.join(config_dir, "life2tea.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("models_dir", "")
        except Exception:
            pass
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    print("[LIFECYCLE] lifespan started", flush=True)
    config_dir = _get_config_dir()
    log_dir = _get_log_dir()
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    # Initialize all managers and store them in app.state
    app.state.config_mgr = ConfigManager(config_dir)
    init_logger_manager(log_dir, retention_days=30)
    app.state.logger_mgr = get_logger_manager()
    app.state.metrics_collector = MetricsCollector()
    app.state.lifecycle_mgr = PluginLifecycleManager(log_dir)
    app.state.model_registry = ModelRegistry(_get_models_dir())
    from app.core.routing import SystemRouter
    app.state.system_router = SystemRouter()

    # Initialize plugin registry: manifests first, GGUF files as fallback.
    from app.plugins.registry import PluginRegistry
    models_dir = _get_models_dir()
    root = Path(PROJECT_ROOT)
    plugin_roots = [str(root / "plugins" / "models"),
                    str(root / "plugins" / "experts")]
    app.state.plugin_registry = PluginRegistry(
        plugin_roots, env={"MODELS_DIR": models_dir or ""}, repo_root=str(root)
    )
    app.state.plugin_registry.discover_with_gguf_fallback(models_dir)

    logger = app.state.logger_mgr
    logger.info("system", f"Life2Tea backend starting (project root: {PROJECT_ROOT})")
    logger.info("system", f"Config dir: {config_dir}")
    logger.info("system", f"Log dir: {log_dir}")

    # Auto-scan models if dir is configured (legacy GGUF index, kept for compat)
    if models_dir and os.path.isdir(models_dir):
        app.state.model_registry.scan()
        n_plugins = len([d for d in app.state.plugin_registry.list_plugins(type="model")])
        logger.info("system", f"Scanned models dir: {models_dir}, found "
                    f"{len(app.state.model_registry.list_models())} models, "
                    f"{n_plugins} plugin descriptors")

    # ── Initialize API key manager ──
    from app.core.api_keys import init_api_key_manager
    init_api_key_manager(app.state.config_mgr)

    # ── Include routers after managers are initialized ──
    from app.routers import config_router, models_router, plugins_router
    from app.routers import chat_router, metrics_router, logs_router, routing_router
    from app.routers import api_keys_router

    app.include_router(api_keys_router, prefix="/api/keys", tags=["API Keys"])
    app.include_router(config_router, prefix="/api/config", tags=["Config"])
    app.include_router(models_router, prefix="/api/models", tags=["Models"])
    app.include_router(plugins_router, prefix="/api/plugins", tags=["Plugins"])
    app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
    app.include_router(metrics_router, prefix="/api/metrics", tags=["Metrics"])
    app.include_router(logs_router, prefix="/api/logs", tags=["Logs"])
    app.include_router(routing_router, prefix="/api/router", tags=["Router"])
    print("[LIFECYCLE] Routers registered, total routes:", len(app.routes))
    # Print all routes that have a path attribute
    for r in app.routes:
        if hasattr(r, 'path'):
            print("  -", r.path)
        elif hasattr(r, 'routes'):  # IncludedRouter
            for sr in r.routes:
                if hasattr(sr, 'path'):
                    print("  -", sr.path)

    logger.info("system", "Life2Tea backend started successfully")
    yield

    # ── Shutdown ───────────────────────────────────────
    logger.info("system", "Life2Tea backend shutting down")
    app.state.lifecycle_mgr.stop_all()
    logger.info("system", "Life2Tea backend stopped")


# ── Create FastAPI app ─────────────────────────────────
app = FastAPI(
    title="Life2Tea API",
    description="Life2Tea — Local LLM Plugin Architecture Backend",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

# CORS — local desktop app only. Vite dev server (5005), Electron/Tauri

# ── Add API Key middleware (before routers) ──
# Must be added before lifespan runs (after app creation)
from app.core.api_keys_middleware import ApiKeyMiddleware
app.add_middleware(ApiKeyMiddleware)
# (file://), and loopback origins are the legitimate clients.
_LOCAL_ORIGINS = [
    "http://127.0.0.1:5005",
    "http://localhost:5005",
    "http://127.0.0.1:3003",
    "http://localhost:3003",
    "null",  # file:// origin serialized by some Electron shells
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS,
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
        "/api/router",
    ],
}


# ── Server entry point ────────────────────────────────
def start_server(host: str = "127.0.0.1", port: int = 3003):
    """Start the FastAPI server (blocking)."""
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    # Read config directly (app.state not yet initialized)
    config_dir = _get_config_dir()
    config_path = os.path.join(config_dir, "life2tea.json")
    cfg = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    host = cfg.get("default_host", "127.0.0.1")
    # Priority: env LIFE2TEA_PORT > config backend_port > default 3003
    port = int(os.environ.get("LIFE2TEA_PORT", cfg.get("backend_port", 3003)))
    print(f"[MAIN] Starting on {host}:{port}", flush=True)
    start_server(host=host, port=port)
