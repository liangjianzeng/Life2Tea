"""
user_service.py — User authentication and management.

Handles:
- User creation (admin setup)
- Password hashing (bcrypt)
- Login/logout
- Session management
"""

import hashlib
import secrets
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from ..core.database import Database, get_db


@dataclass
class User:
    """User account."""
    id: str
    email: str
    password_hash: str
    is_admin: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "is_admin": self.is_admin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def hash_password(password: str) -> str:
    """Hash a password using SHA256 with salt."""
    salt = secrets.token_hex(16)
    # Simple but effective: salt + hash
    hash_val = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hash_val}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    if ":" not in password_hash:
        return False
    salt, expected_hash = password_hash.split(":", 1)
    actual_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return actual_hash == expected_hash


class UserService:
    """Manages user accounts and authentication."""

    def __init__(self, db: Database):
        self.db = db

    def is_initialized(self) -> bool:
        """Check if any users exist."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            conn.close()

    def create_admin(self, email: str, password: str) -> User:
        """Create the first admin user."""
        if self.is_initialized():
            raise ValueError("Admin user already exists")

        user_id = secrets.token_hex(8)
        password_hash = hash_password(password)
        now = time.time()

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (id, email, password_hash, is_admin, created_at, updated_at) "
                "VALUES (?, ?, ?, 1, ?, ?)",
                (user_id, email, password_hash, now, now),
            )
            conn.commit()
            return User(
                id=user_id,
                email=email,
                password_hash=password_hash,
                is_admin=True,
                created_at=now,
                updated_at=now,
            )
        finally:
            conn.close()

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            )
            row = cursor.fetchone()
            if row is None:
                return None

            if not verify_password(password, row["password_hash"]):
                return None

            return User(
                id=row["id"],
                email=row["email"],
                password_hash=row["password_hash"],
                is_admin=bool(row["is_admin"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        finally:
            conn.close()

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return User(
                id=row["id"],
                email=row["email"],
                password_hash=row["password_hash"],
                is_admin=bool(row["is_admin"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        finally:
            conn.close()

    def create_session(self, user_id: str) -> str:
        """Create a new session for a user. Returns session ID."""
        session_id = secrets.token_hex(16)
        now = time.time()
        expires_at = now + 86400 * 7  # 7 days

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, user_id, now, expires_at),
            )
            conn.commit()
            return session_id
        finally:
            conn.close()

    def validate_session(self, session_id: str) -> Optional[User]:
        """Validate a session ID and return the user if valid."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT s.user_id FROM sessions s "
                "WHERE s.id = ? AND s.expires_at > ?",
                (session_id, time.time()),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self.get_user(row["user_id"])
        finally:
            conn.close()

    def revoke_session(self, session_id: str):
        """Revoke a session (logout)."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()


# Global instance
_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    """Get the global user service instance."""
    global _user_service
    if _user_service is None:
        raise RuntimeError("UserService not initialized")
    return _user_service


def init_user_service(db: Database) -> UserService:
    """Initialize the global user service."""
    global _user_service
    _user_service = UserService(db)
    return _user_service


__all__ = [
    "User",
    "UserService",
    "hash_password",
    "verify_password",
    "get_user_service",
    "init_user_service",
]
