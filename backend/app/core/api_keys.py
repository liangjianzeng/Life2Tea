"""
api_keys.py — API Key management module.

Implements OpenAPI-style API key authentication:
  - Keys are UUID4 strings (128-bit random)
  - Each key has scopes, expiration, metadata
  - Stored in memory (or persist to config/life2tea.json)

Security notes:
  - Keys are hashed before storage (using SHA256)
  - Plain keys are only shown once at creation
  - No key recovery possible (delete and recreate if lost)
"""

import secrets
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from ..main import get_config_mgr
from ..core.config import ConfigManager


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
    id: str                           # UUID4 string (not hashed)
    hashed_key: str                   # SHA256 hash of key
    name: str                         # User-friendly name
    scopes: List[Scope]               # Permissions
    created_at: float                 # Unix timestamp
    expires_at: Optional[float] = None  # Unix timestamp (None = never)
    last_used_at: Optional[float] = None  # Last usage timestamp
    revoked: bool = False             # If True, key is disabled

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
    ) -> "ApiKey":
        """Create a new API key."""
        key = secrets.token_hex(16)  # 32-char hex string
        hashed = hashlib.sha256(key.encode()).hexdigest()

        now = time.time()
        expires = now + expires_in_days * 86400 if expires_in_days else None

        return cls(
            id=secrets.token_hex(8),  # 16-char ID
            hashed_key=hashed,
            name=name,
            scopes=scopes,
            created_at=now,
            expires_at=expires,
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
        }
        if include_plain_key:
            data["key"] = self.hashed_key  # Note: This is the *hash*, not plain key
        return data


class ApiKeyManager:
    """Manages API keys in memory with optional config persistence."""

    def __init__(self, config_mgr: ConfigManager):
        self.config_mgr = config_mgr
        self._keys: Dict[str, ApiKey] = {}  # id -> ApiKey
        self._key_to_id: Dict[str, str] = {}  # hashed_key -> id
        self._load()

    def _load(self):
        """Load keys from config."""
        cfg = self.config_mgr.get_global()
        keys_data = cfg.get("api_keys", [])

        for data in keys_data:
            try:
                key = ApiKey(
                    id=data["id"],
                    hashed_key=data["hashed_key"],
                    name=data["name"],
                    scopes=[Scope(s) for s in data.get("scopes", [])],
                    created_at=data["created_at"],
                    expires_at=data.get("expires_at"),
                    last_used_at=data.get("last_used_at"),
                    revoked=data.get("revoked", False),
                )
                self._keys[key.id] = key
                self._key_to_id[key.hashed_key] = key.id
            except Exception as e:
                print(f"Warning: Failed to load API key: {e}")

    def _save(self):
        """Persist keys to config."""
        keys_data = []
        for key in self._keys.values():
            keys_data.append({
                "id": key.id,
                "hashed_key": key.hashed_key,
                "name": key.name,
                "scopes": [s.value for s in key.scopes],
                "created_at": key.created_at,
                "expires_at": key.expires_at,
                "last_used_at": key.last_used_at,
                "revoked": key.revoked,
            })
        cfg = self.config_mgr.get_global()
        cfg["api_keys"] = keys_data
        self.config_mgr.update_global(cfg)

    def generate_key(
        self,
        name: str,
        scopes: List[Scope],
        expires_in_days: Optional[int] = None,
    ) -> tuple[str, ApiKey]:
        """Generate a new API key. Returns (plain_key, api_key_obj).

        IMPORTANT: The plain key should only be shown once!
        """
        key_obj = ApiKey.create(name, scopes, expires_in_days)
        plain_key = hashlib.sha256(key_obj.hashed_key.encode()).hexdigest()

        self._keys[key_obj.id] = key_obj
        self._key_to_id[key_obj.hashed_key] = key_obj.id
        self._save()

        return plain_key, key_obj

    def get_key_by_id(self, key_id: str) -> Optional[ApiKey]:
        """Get key by ID."""
        return self._keys.get(key_id)

    def get_key_by_hash(self, hashed_key: str) -> Optional[ApiKey]:
        """Get key by hashed value."""
        key_id = self._key_to_id.get(hashed_key)
        return self._keys.get(key_id) if key_id else None

    def list_keys(self) -> List[ApiKey]:
        """List all keys."""
        return list(self._keys.values())

    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key by ID."""
        if key_id in self._keys:
            self._keys[key_id].revoked = True
            self._save()
            return True
        return False

    def delete_key(self, key_id: str) -> bool:
        """Delete a key permanently."""
        if key_id in self._keys:
            key = self._keys.pop(key_id)
            self._key_to_id.pop(key.hashed_key, None)
            self._save()
            return True
        return False

    def verify_key(self, authorization_header: str) -> Optional[ApiKey]:
        """Verify API key from Authorization header.

        Expected format: "Bearer <hashed_key>"

        Returns the ApiKey if valid, None otherwise.
        """
        if not authorization_header.startswith("Bearer "):
            return None

        provided_hash = authorization_header[7:].strip()

        # Check if it's a valid hash (64 hex chars)
        if len(provided_hash) != 64:
            return None

        try:
            int(provided_hash, 16)  # Validate hex
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
        self._save()

        return key


# Global singleton (will be initialized in main.py)
_api_key_manager: Optional[ApiKeyManager] = None


def get_api_key_manager() -> ApiKeyManager:
    """Get the global API key manager instance."""
    global _api_key_manager
    if _api_key_manager is None:
        from ..main import get_config_mgr
        _api_key_manager = ApiKeyManager(get_config_mgr())
    return _api_key_manager


def init_api_key_manager(config_mgr: ConfigManager):
    """Initialize the global API key manager."""
    global _api_key_manager
    _api_key_manager = ApiKeyManager(config_mgr)


__all__ = [
    "ApiKey",
    "Scope",
    "ApiKeyManager",
    "get_api_key_manager",
    "init_api_key_manager",
]
