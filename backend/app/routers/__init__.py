"""
routers/__init__.py — Router package exports.

All routers are imported here so main.py can do:
    from app.routers import config_router, models_router, ...
"""

from .config_router import router as config_router
from .models_router import router as models_router
from .plugins_router import router as plugins_router
from .chat_router import router as chat_router
from .metrics_router import router as metrics_router
from .logs_router import router as logs_router
from .routing_router import router as routing_router
from .api_keys_router import router as api_keys_router
from .auth_router import router as auth_router

__all__ = [
    "config_router",
    "models_router",
    "plugins_router",
    "chat_router",
    "metrics_router",
    "logs_router",
    "routing_router",
    "api_keys_router",
]
