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
from app.core.database import init_db, get_db
from app.core.user_service import init_user_service, get_user_service

# ── Initialize database and user service at module level ──
# This ensures they're available before lifespan runs (needed for middleware)
config_dir = os.path.join(PROJECT_ROOT, "config")
os.makedirs(config_dir, exist_ok=True)
init_db(config_dir)
# Stub logger for user_service lazy import
class _StubLogger:
    def info(self, source, msg, *args, **kwargs):
        print(f"[{source}] {msg}", *args, **kwargs)

logger = _StubLogger()

init_user_service(get_db())
print(f"[Main] Database initialized: {get_db().db_path}")
print(f"[Main] UserService initialized")
from app.core.logger import (
    LoggerManager, init_logger_manager, get_logger_manager
)
from app.core.metrics import MetricsCollector
from app.core.stats_service import StatsService
from app.core.model_router import ModelRouter


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


def get_stats_service(request: Request = None) -> StatsService:
    state = _get_state(request)
    mgr = getattr(state, "stats_service", None)
    if mgr is None:
        raise RuntimeError("StatsService not initialized")
    return mgr


def get_model_router(request: Request = None) -> ModelRouter:
    state = _get_state(request)
    mgr = getattr(state, "model_router", None)
    if mgr is None:
        raise RuntimeError("ModelRouter not initialized")
    return mgr


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

    # Database and UserService already initialized at module level
    app.state.db = get_db()
    app.state.user_service = get_user_service()

    # Initialize logging service
    from app.core.logging_service import init_logging_service
    app.state.logging_service = init_logging_service(config_dir)

    # Initialize all managers and store them in app.state
    try:
        app.state.config_mgr = ConfigManager(config_dir)
        init_logger_manager(log_dir, retention_days=30)
        app.state.logger_mgr = get_logger_manager()
        app.state.metrics_collector = MetricsCollector()
        # Initialize StatsService
        from app.core.stats_middleware import register_stats_service
        app.state.stats_service = StatsService(app.state.db)
        app.state.stats_service.create_tables()
        register_stats_service(app.state.stats_service)
        # Initialize ModelRouter for unified routing
        from app.core.model_router import init_model_router
        app.state.model_router = init_model_router(
            config_mgr=app.state.config_mgr,
            stats_service=app.state.stats_service,
        )

        # ── Unified Model Gateway (provider-abstraction + router) ──
        from app.gateway import ProviderManager
        from app.gateway.router_api import init_gateway
        app.state.provider_manager = ProviderManager(
            config_path=os.path.join(config_dir, "gateway.json"),
            config_mgr=app.state.config_mgr,
        )
        app.state.gateway = init_gateway(app.state.provider_manager)
    except Exception as e:
        print(f"[LIFECYCLE] Error during initialization: {e}", flush=True)
        raise

    logger = app.state.logger_mgr
    logger.info("system", f"Life2Tea backend starting (project root: {PROJECT_ROOT})")
    logger.info("system", f"Config dir: {config_dir}")
    logger.info("system", f"Log dir: {log_dir}")

    # Log configured gateway providers
    providers = app.state.provider_manager.get_config().get("providers", {})
    logger.info("system", f"Configured model endpoints: {len(providers)}")

    # ── Initialize API key manager ──
    print("[LIFECYCLE] Initializing API key manager...", flush=True)
    from app.core.api_keys import init_api_key_manager
    init_api_key_manager(app.state.db)

    # ── Add api_keys_router routes (after managers initialized) ──
    print("[LIFECYCLE] Adding API keys routes...", flush=True)
    _add_api_keys_routes()

    # ── Include other routers after managers are initialized ──
    print("[LIFECYCLE] Including routers...", flush=True)
    from app.routers import config_router, models_router
    from app.routers import chat_router, metrics_router, logs_router, routing_router
    from app.routers import auth_router, stats_router
    
    from app.gateway.router_api import gateway_router
    from app.routers.log_router import router as log_router
    from app.routers.model_router_router import router as model_router_router

    app.include_router(config_router, prefix="/api/config", tags=["Config"])
    app.include_router(models_router, prefix="/api/models", tags=["Models"])
    app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
    app.include_router(metrics_router, prefix="/api/metrics", tags=["Metrics"])
    app.include_router(logs_router, prefix="/api/logs", tags=["Logs"])
    app.include_router(log_router, tags=["Logs"])
    app.include_router(routing_router, prefix="/api/router", tags=["Router"])
    app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
    app.include_router(stats_router.router)
    app.include_router(model_router_router, prefix="/api/model-router", tags=["ModelRouter"])
    app.include_router(gateway_router)
    print("[LIFECYCLE] Routers registered, total routes:", len(app.routes), flush=True)
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
    if hasattr(app.state, "provider_manager"):
        import asyncio

        try:
            asyncio.get_event_loop().run_until_complete(app.state.provider_manager.stop_all())
        except Exception:
            pass
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
from app.core.api_keys_middleware import AuthMiddleware
# app.add_middleware(AuthMiddleware)

from app.core.stats_middleware import StatsMiddleware
app.add_middleware(StatsMiddleware)
# (file://), and loopback origins are the legitimate clients.
_LOCAL_ORIGINS = [
    "http://127.0.0.1:5005",
    "http://localhost:5005",
    "http://100.81.83.59:5005",
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


# ── Add api_keys_router routes (after app.state is initialized) ──
# Must be done after lifespan initializes config_mgr
def _add_api_keys_routes():
    """Add api_keys_router routes to app. Called during lifespan."""
    from app.routers import api_keys_router
    for route in api_keys_router.routes:
        path = "/api/keys" + (route.path or "")
        app.add_api_route(path, route.endpoint, methods=list(route.methods or []), tags=["API Keys"])


# ── Server entry point ────────────────────────────────
def start_server(host: str = "127.0.0.1", port: int = 3003):
    """Start the FastAPI server (blocking)."""
    uvicorn.run(app, host=host, port=port, log_level="info")


# ── Server entry point ──
# Routes are registered during lifespan startup.


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
