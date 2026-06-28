"""
api_keys_middleware.py — API Key authentication middleware.

Validates API keys from the Authorization header:
  - Header format: "Authorization: Bearer <hashed_key>"
  - If no key or invalid key, returns 401 Unauthorized
  - If key has insufficient scopes, returns 403 Forbidden

Usage in FastAPI:
    app.add_middleware(ApiKeyMiddleware)
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from typing import Optional


class ApiKeyMiddleware:
    """Middleware to enforce API key authentication."""

    EXCLUDE_PATHS = {
        "/",
        "/docs",
        "/openapi.json",
        "/health",
        "/api/health",
        "/api/models",  # Allow read-only for unauthenticated users
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path
        method = scope.get("method", "GET")

        # Skip auth for excluded paths
        if any(path.startswith(excl) for excl in self.EXCLUDE_PATHS):
            await self.app(scope, receive, send)
            return

        # POST /api/keys is allowed for key creation (first key)
        if path == "/api/keys" and method == "POST":
            # Allow key creation if manager not initialized or no keys exist
            try:
                from .api_keys import get_api_key_manager
                manager = get_api_key_manager()
                if manager is None or not manager.list_keys():
                    await self.app(scope, receive, send)
                    return
            except Exception:
                await self.app(scope, receive, send)
                return

        # Validate API key for all other requests
        auth_header = request.headers.get("Authorization", "")
        key = self._validate_key(auth_header, path)

        if key is None:
            response = JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Invalid or missing API key",
                },
            )
            await response(scope, receive, send)
            return

        # Check scopes for protected endpoints
        if not self._check_scopes(key, path):
            response = JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden",
                    "message": "Insufficient scopes.",
                },
            )
            await response(scope, receive, send)
            return

        # Add key info to request state for downstream use
        request.state.api_key = key

        # Continue with request
        await self.app(scope, receive, send)

    def _validate_key(self, auth_header: str, path: str) -> Optional["ApiKey"]:
        """Validate API key and return the ApiKey object if valid."""
        if not auth_header.startswith("Bearer "):
            return None

        try:
            from .api_keys import get_api_key_manager
            manager = get_api_key_manager()
            return manager.verify_key(auth_header)
        except Exception:
            return None

    def _check_scopes(self, key: "ApiKey", path: str) -> bool:
        """Check if key has sufficient scopes for the endpoint."""
        required = self._get_required_scopes(path)

        if not required:
            return True

        key_scopes = set(key.scopes)
        return any(req in key_scopes for req in required)

    def _get_required_scopes(self, path: str) -> list:
        """Determine required scopes for a given path."""
        if path.startswith("/api/keys"):
            from .api_keys import Scope
            return [Scope.ADMIN]
        if path.startswith("/api/chat"):
            from .api_keys import Scope
            return [Scope.CHAT]
        if path.startswith("/api/models") and path != "/api/models":
            from .api_keys import Scope
            if "load" in path or "unload" in path:
                return [Scope.MODELS_WRITE]
            return [Scope.MODELS_READ]
        return []


__all__ = ["ApiKeyMiddleware"]
