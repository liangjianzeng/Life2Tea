"""
api_keys.py — API Key management with SQLite persistence.

Implements OpenAPI-style API key authentication:
  - Keys are UUID4 strings (128-bit random)
  - Each key has scopes, expiration, metadata
  - Stored in SQLite database

Security notes:
  - Keys are hashed before storage (using SHA256)
  - Plain keys are only shown once at creation
  - No key recovery possible (delete and recreate if lost)
"""

import secrets
import hashlib
import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from ..core.database import Database, get_db


class Scope(str, Enum):
    """API scopes (permissions)."""
    READ = "read"
    WRITE = "write"
    MODELS_READ = "models:read"
    MODELS_WRITE = "models:write"
    CHAT = "chat:infer"
    ADMIN = "admin"


@dataclass
class ApiKey:
    """API key with metadata."""
    id: str
    hashed_key: str
    name: str
    scopes: List[Scope]
    created_at: float
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None
    revoked: bool = False
    owner_id: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def remaining_days(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        return int((self.expires_at - time.time()) / 86400)

    @classmethod
    def create(
        cls,
        name: str,
        scopes: List[Scope],
        expires_in_days: Optional[int] = None,
        owner_id: Optional[str] = None,
    ) -> "ApiKey":
        """Create a new API key."""
        key = secrets.token_hex(16)
        hashed = hashlib.sha256(key.encode()).hexdigest()

        now = time.time()
        expires = now + expires_in_days * 86400 if expires_in_days else None

        return cls(
            id=secrets.token_hex(8),
            hashed_key=hashed,
            name=name,
            scopes=scopes,
            created_at=now,
            expires_at=expires,
            owner_id=owner_id,
        )

    def to_dict(self, include_plain_key: bool = False) -> dict:
        """Serialize to dict. Plain key only included once at creation."""
        data = {
            "id": self.id,
            "name": self.name,
            "scopes": [s.value for s in self.scopes],
            "created_at": self.created_at,
            "created_at_iso": datetime.fromtimestamp(
                self.created_at, tz=timezone.utc
            ).isoformat(),
            "expires_at": self.expires_at,
            "expires_at_iso": (
                datetime.fromtimestamp(self.expires_at, tz=timezone.utc).isoformat()
                if self.expires_at else None
            ),
            "remaining_days": self.remaining_days,
            "revoked": self.revoked,
            "owner_id": self.owner_id,
        }
        if include_plain_key:
            data["key"] = self.hashed_key
        return data


class ApiKeyManager:
    """Manages API keys in SQLite."""

    def __init__(self, db: Database):
        self.db = db

    def _key_to_row(self, key: ApiKey) -> dict:
        """Convert ApiKey to database row dict."""
        return {
            "id": key.id,
            "name": key.name,
            "hashed_key": key.hashed_key,
            "scopes": json.dumps([s.value for s in key.scopes]),
            "created_at": key.created_at,
            "expires_at": key.expires_at,
            "last_used_at": key.last_used_at,
            "revoked": 1 if key.revoked else 0,
            "owner_id": key.owner_id,
        }

    def _row_to_key(self, row) -> ApiKey:
        """Convert database row to ApiKey."""
        return ApiKey(
            id=row["id"],
            hashed_key=row["hashed_key"],
            name=row["name"],
            scopes=[Scope(s) for s in json.loads(row["scopes"])],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            revoked=bool(row["revoked"]),
            owner_id=row["owner_id"],
        )

    def generate_key(
        self,
        name: str,
        scopes: List[Scope],
        expires_in_days: Optional[int] = None,
        owner_id: Optional[str] = None,
    ) -> tuple[str, ApiKey]:
        """Generate a new API key. Returns (plain_key, api_key_obj)."""
        key_obj = ApiKey.create(name, scopes, expires_in_days, owner_id)
        plain_key = key_obj.hashed_key

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO api_keys (id, name, hashed_key, scopes, created_at, expires_at, last_used_at, revoked, owner_id) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?)",
                (
                    key_obj.id,
                    key_obj.name,
                    key_obj.hashed_key,
                    json.dumps([s.value for s in key_obj.scopes]),
                    key_obj.created_at,
                    key_obj.expires_at,
                    key_obj.owner_id,
                ),
            )
            conn.commit()
            return plain_key, key_obj
        finally:
            conn.close()

    def get_key_by_id(self, key_id: str) -> Optional[ApiKey]:
        """Get key by ID."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_key(row)
        finally:
            conn.close()

    def get_key_by_hash(self, hashed_key: str) -> Optional[ApiKey]:
        """Get key by hashed value."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_keys WHERE hashed_key = ?", (hashed_key,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_key(row)
        finally:
            conn.close()

    def list_keys(self, owner_id: Optional[str] = None) -> List[ApiKey]:
        """List all keys, optionally filtered by owner."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            if owner_id:
                cursor.execute(
                    "SELECT * FROM api_keys WHERE owner_id = ? ORDER BY created_at DESC",
                    (owner_id,),
                )
            else:
                cursor.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
            return [self._row_to_key(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key by ID."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (key_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_key(self, key_id: str) -> bool:
        """Delete a key permanently."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def verify_key(self, authorization_header: str) -> Optional[ApiKey]:
        """Verify API key from Authorization header.

        Expected format: "Bearer <hashed_key>"
        """
        if not authorization_header.startswith("Bearer "):
            return None

        provided_hash = authorization_header[7:].strip()

        if len(provided_hash) != 64:
            return None

        try:
            int(provided_hash, 16)
        except ValueError:
            return None

        key = self.get_key_by_hash(provided_hash)
        if key is None:
            return None

        if key.revoked:
            return None

        if key.is_expired:
            return None

        # Update last used time
        key.last_used_at = time.time()
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (key.last_used_at, key.id),
            )
            conn.commit()
        finally:
            conn.close()

        return key


# Global instance
_api_key_manager: Optional[ApiKeyManager] = None


def get_api_key_manager() -> ApiKeyManager:
    """Get the global API key manager instance."""
    global _api_key_manager
    if _api_key_manager is None:
        raise RuntimeError("ApiKeyManager not initialized")
    return _api_key_manager


def init_api_key_manager(db: Database) -> ApiKeyManager:
    """Initialize the global API key manager."""
    global _api_key_manager
    _api_key_manager = ApiKeyManager(db)
    return _api_key_manager


__all__ = [
    "ApiKey",
    "Scope",
    "ApiKeyManager",
    "get_api_key_manager",
    "init_api_key_manager",
]
