"""
api_keys_middleware.py — API Key authentication middleware.

Validates API keys from the Authorization header:
  - Header format: "Authorization: Bearer <hashed_key>"
  - If no key or invalid key, returns 401 Unauthorized
  - If key has insufficient scopes, returns 403 Forbidden

Usage in FastAPI:
    app.add_middleware(ApiKeyMiddleware)
"""

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional

from .api_keys import ApiKey, Scope, get_api_key_manager


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

        # Skip auth for excluded paths
        if any(path.startswith(excl) for excl in self.EXCLUDE_PATHS):
            await self.app(scope, receive, send)
            return

        # Validate API key
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
                    "message": f"Insufficient scopes. Required: {self._get_required_scopes(path)}",
                },
            )
            await response(scope, receive, send)
            return

        # Add key info to request state for downstream use
        request.state.api_key = key

        # Continue with request
        await self.app(scope, receive, send)

    def _validate_key(self, auth_header: str, path: str) -> Optional[ApiKey]:
        """Validate API key and return the ApiKey object if valid."""
        if not auth_header.startswith("Bearer "):
            # Allow without key for read-only endpoints
            if path in {"/api/models", "/api/models/scan"}:
                return None
            return None

        try:
            manager = get_api_key_manager()
            return manager.verify_key(auth_header)
        except Exception:
            return None

    def _check_scopes(self, key: ApiKey, path: str) -> bool:
        """Check if key has sufficient scopes for the endpoint."""
        required = self._get_required_scopes(path)

        if not required:
            return True  # No scope required

        key_scopes = set(key.scopes)
        return any(req in key_scopes for req in required)

    def _get_required_scopes(self, path: str) -> list:
        """Determine required scopes for a given path."""
        # Admin endpoints
        if path.startswith("/api/keys"):
            return [Scope.ADMIN]

        # Chat endpoints
        if path.startswith("/api/chat"):
            return [Scope.CHAT]

        # Model management endpoints
        if path.startswith("/api/models") and path != "/api/models":
            if "load" in path or "unload" in path:
                return [Scope.MODELS_WRITE]
            return [Scope.MODELS_READ]

        return []  # No scope required for public endpoints


__all__ = ["ApiKeyMiddleware"]
