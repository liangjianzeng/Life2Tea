"""
api_keys_middleware.py — Authentication middleware.

Supports two auth methods:
1. API Key (Bearer token) — for programmatic access
2. Session Cookie — for web UI access

Validates API keys from the Authorization header:
  - Header format: "Authorization: Bearer <hashed_key>"
  - Session cookie: "life2tea_session"
  - If no key or invalid key, returns 401 Unauthorized
  - If key has insufficient scopes, returns 403 Forbidden
"""

import json
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, Response
from typing import Optional


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication (API key or session cookie)."""

    EXCLUDE_PATHS = {
        "/docs",
        "/openapi.json",
        "/health",
        "/api/health",
        "/api/config/dirs/list",
        "/api/config/dirs/exists",
        "/api/stats/system",
        "/api/stats/resources",
        "/api/stats/dashboard",
        "/api/stats/performance",
        "/api/stats/api-keys",
        "/api/stats/requests",
        "/api/stats/recent-logs",
        "/api/stats/key-detail",
        "/api/stats/token-usage",
        "/api/stats/model-metrics",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        print(f"*** AuthMiddleware DISPATCH CALLED *** {method} {path}", flush=True)
        print(f"*** EXCLUDE_PATHS: {self.EXCLUDE_PATHS}", flush=True)

        # Skip auth for excluded paths and auth endpoints
        print(f"[AuthMiddleware] Checking path: {path}", flush=True)
        print(f"[AuthMiddleware] EXCLUDE_PATHS: {self.EXCLUDE_PATHS}", flush=True)
        if path in self.EXCLUDE_PATHS:
            print(f"[AuthMiddleware] EXCLUDED: {path}", flush=True)
            return await call_next(request)

        # Allow auth endpoints
        if path.startswith("/api/auth"):
            print(f"[AuthMiddleware] AUTH ENDPOINT: {path}", flush=True)
            return await call_next(request)

        # Allow static files for frontend
        if path.startswith("/static") or path.startswith("/assets"):
            print(f"[AuthMiddleware] STATIC: {path}", flush=True)
            return await call_next(request)

        # Allow frontend SPA root
        if path == "/":
            print(f"[AuthMiddleware] SPA ROOT: {path}", flush=True)
            return await call_next(request)

        # Check for session cookie (web UI)
        session_id = request.cookies.get("life2tea_session")
        print(f"[AuthMiddleware] session_id={session_id}", flush=True)
        if session_id:
            from app.core.user_service import get_user_service
            user_service = get_user_service()
            user = user_service.validate_session(session_id)
            print(f"[AuthMiddleware] validated={user is not None} for {method} {path}", flush=True)
            if user:
                request.state.current_user = user
                print(f"[AuthMiddleware] ALLOWED: {method} {path} (session)", flush=True)
                return await call_next(request)

        # Check for API Key (Bearer token)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            key = self._validate_key(auth_header, path)
            if key:
                if self._check_scopes(key, path):
                    request.state.api_key = key
                    return await call_next(request)
                else:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": "forbidden",
                            "message": "Insufficient scopes.",
                        },
                    )

        # Allow POST /api/keys for key creation (first key)
        if path == "/api/keys" and method == "POST":
            from app.core.api_keys import get_api_key_manager
            manager = get_api_key_manager()
            if not manager.list_keys():
                return await call_next(request)

        # No auth — return 401
        return JSONResponse(
            status_code=401,
            content={
                "error": "unauthorized",
                "message": "Authentication required",
            },
        )

    def _validate_key(self, auth_header: str, path: str) -> Optional["ApiKey"]:
        """Validate API key and return the ApiKey object if valid."""
        if not auth_header.startswith("Bearer "):
            return None

        try:
            from app.core.api_keys import get_api_key_manager
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
            from app.core.api_keys import Scope
            return [Scope.ADMIN]
        if path.startswith("/api/chat"):
            from app.core.api_keys import Scope
            return [Scope.CHAT]
        if path.startswith("/api/models") and path != "/api/models":
            from app.core.api_keys import Scope
            if "load" in path or "unload" in path:
                return [Scope.MODELS_WRITE]
            return [Scope.MODELS_READ]
        return []
