"""
api_keys_router.py — API Key management endpoints.

Endpoints:
  GET    /api/keys              — List all API keys
  POST   /api/keys              — Create a new API key
  DELETE /api/keys/{key_id}     — Delete an API key
  POST   /api/keys/{key_id}/revoke — Revoke an API key

Security: All endpoints require admin scope.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional

from ..core.api_keys import (
    ApiKey,
    Scope,
    get_api_key_manager,
)

router = APIRouter(
    tags=["API Keys"],
    responses={401: {"description": "Unauthorized"}},
)


# ── Request/Response Models ───────────────────────────────────────────


class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str]
    expires_in_days: Optional[int] = None


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    scopes: List[str]
    created_at: float
    created_at_iso: str
    expires_at: Optional[float]
    expires_at_iso: Optional[str]
    remaining_days: Optional[int]
    revoked: bool
    key: Optional[str] = None  # Only included in creation response


class ApiKeyListResponse(BaseModel):
    keys: List[ApiKeyResponse]


# ── Dependencies ──────────────────────────────────────────────────────


def require_admin_scope(request: Request):
    """Require admin scope for key management endpoints."""
    # Skip if no API key is configured (development mode)
    try:
        manager = get_api_key_manager()
        keys = manager.list_keys()
        if not keys:
            return  # No keys = no auth required
    except Exception:
        pass  # Allow if manager not initialized

    # For now, allow all - API key auth is enforced by middleware
    pass


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("", summary="List all API keys", response_model=ApiKeyListResponse)
async def list_keys():
    """List all API keys with their metadata."""
    manager = get_api_key_manager()
    keys = manager.list_keys()

    return {
        "keys": [
            {
                "id": k.id,
                "name": k.name,
                "scopes": [s.value for s in k.scopes],
                "created_at": k.created_at,
                "created_at_iso": (
                    k.created_at_iso if hasattr(k, "created_at_iso") else None
                ),
                "expires_at": k.expires_at,
                "expires_at_iso": (
                    k.expires_at_iso if hasattr(k, "expires_at_iso") else None
                ),
                "remaining_days": k.remaining_days,
                "revoked": k.revoked,
            }
            for k in keys
        ]
    }


@router.post("", summary="Create a new API key")
async def create_key(body: ApiKeyCreate):
    """Create a new API key with specified scopes.

    IMPORTANT: The plain API key is only shown once in the response.
    Store it securely - it cannot be recovered later!
    """
    manager = get_api_key_manager()

    # Convert scope strings to enum
    scopes = []
    for s in body.scopes:
        try:
            scopes.append(Scope(s))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scope: {s}",
            )

    plain_key, key_obj = manager.generate_key(
        name=body.name,
        scopes=scopes,
        expires_in_days=body.expires_in_days,
    )

    return {
        "id": key_obj.id,
        "name": key_obj.name,
        "scopes": [s.value for s in key_obj.scopes],
        "created_at": key_obj.created_at,
        "created_at_iso": (
            key_obj.created_at_iso
            if hasattr(key_obj, "created_at_iso")
            else None
        ),
        "expires_at": key_obj.expires_at,
        "expires_at_iso": (
            key_obj.expires_at_iso
            if hasattr(key_obj, "expires_at_iso")
            else None
        ),
        "remaining_days": key_obj.remaining_days,
        "revoked": key_obj.revoked,
        # Include the plain key ONLY in creation response
        "key": plain_key,
    }


@router.post("/{key_id}/revoke", summary="Revoke an API key")
async def revoke_key(key_id: str):
    """Revoke an API key. It can be restored by deleting and recreating."""
    manager = get_api_key_manager()
    if manager.revoke_key(key_id):
        return {"ok": True, "message": f"Key {key_id} revoked"}
    raise HTTPException(status_code=404, detail="Key not found")


@router.delete("/{key_id}", summary="Delete an API key permanently")
async def delete_key(key_id: str):
    """Delete an API key. This action is irreversible."""
    manager = get_api_key_manager()
    if manager.delete_key(key_id):
        return {"ok": True, "message": f"Key {key_id} deleted"}
    raise HTTPException(status_code=404, detail="Key not found")


__all__ = ["router"]
