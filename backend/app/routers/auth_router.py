"""
auth_router.py — Authentication routes.

Provides:
- POST /api/auth/init — Create admin user (first-time setup)
- POST /api/auth/login — Login with email/password
- POST /api/auth/logout — Logout (revoke session)
- GET /api/auth/whoami — Get current user info
- GET /api/auth/status — Check if admin is initialized
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Cookie, Response
from pydantic import BaseModel, EmailStr
from typing import Optional

from ..core.user_service import (
    UserService, init_user_service, get_user_service, User,
)
from ..core.database import Database, get_db, init_db
from ..core.api_keys import ApiKeyManager, init_api_key_manager, get_api_key_manager


router = APIRouter()


# ── Request/Response Models ──────────────────────────────

class InitRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    session_id: str
    user: dict


class WhoamiResponse(BaseModel):
    user: Optional[dict] = None
    initialized: bool = False


class StatusResponse(BaseModel):
    initialized: bool


# ── Dependency: Get current user from session cookie ──────

async def get_current_user(request: Request, response: Response = None) -> Optional[User]:
    """Extract current user from session cookie."""
    session_id = request.cookies.get("life2tea_session")
    if not session_id:
        return None

    user_service = get_user_service()
    user = user_service.validate_session(session_id)

    if not user:
        # Session invalid, clear cookie
        if response:
            response.delete_cookie("life2tea_session")
        return None

    return user


async def require_admin(request: Request, response: Response = None) -> User:
    """Require authenticated admin user."""
    user = await get_current_user(request, response)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Routes ───────────────────────────────────────────────

@router.get("/status", response_model=StatusResponse)
async def get_status(user_service: UserService = Depends(get_user_service)):
    """Check if admin user is initialized."""
    return StatusResponse(initialized=user_service.is_initialized())


@router.post("/init")
async def init_admin(
    req: InitRequest,
    response: Response,
    user_service: UserService = Depends(get_user_service),
):
    """Create the first admin user."""
    if user_service.is_initialized():
        raise HTTPException(status_code=400, detail="Admin user already exists")

    try:
        user = user_service.create_admin(req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create session
    session_id = user_service.create_session(user.id)
    response.set_cookie(
        key="life2tea_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=7 * 86400,
    )

    return {
        "message": "Admin user created successfully",
        "user": user.to_dict(),
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    response: Response,
    user_service: UserService = Depends(get_user_service),
):
    """Login with email and password."""
    if not user_service.is_initialized():
        raise HTTPException(status_code=400, detail="Admin not initialized")

    user = user_service.authenticate(req.email, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session_id = user_service.create_session(user.id)
    response.set_cookie(
        key="life2tea_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=7 * 86400,
    )

    return LoginResponse(
        session_id=session_id,
        user=user.to_dict(),
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user_service: UserService = Depends(get_user_service),
):
    """Logout and clear session."""
    session_id = request.cookies.get("life2tea_session")
    if session_id:
        user_service.revoke_session(session_id)
    response.delete_cookie("life2tea_session")
    return {"message": "Logged out successfully"}


@router.get("/whoami", response_model=WhoamiResponse)
async def whoami(
    request: Request,
    response: Response = None,
    user_service: UserService = Depends(get_user_service),
):
    """Get current user info."""
    user = await get_current_user(request, response)
    if user:
        return WhoamiResponse(user=user.to_dict(), initialized=True)
    else:
        initialized = user_service.is_initialized()
        return WhoamiResponse(user=None, initialized=initialized)
