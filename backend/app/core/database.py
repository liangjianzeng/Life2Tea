"""
database.py — SQLite database management for Life2Tea.

Provides persistent storage for:
- Users (admin credentials)
- API keys
- Sessions
"""

import sqlite3
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # API keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                hashed_key TEXT NOT NULL UNIQUE,
                scopes TEXT NOT NULL,  -- JSON array
                created_at REAL NOT NULL,
                expires_at REAL,
                last_used_at REAL,
                revoked INTEGER NOT NULL DEFAULT 0,
                owner_id TEXT,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            )
        """)

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                model_family TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        conn.close()

    def get_connection(self) -> sqlite3.Connection:
        """Get a new database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def close(self):
        """Close database (no-op for SQLite)."""
        pass


# Global database instance
_db: Optional[Database] = None


def get_db() -> Database:
    """Get the global database instance."""
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


def init_db(config_dir: str) -> Database:
    """Initialize the global database instance."""
    global _db
    db_path = os.path.join(config_dir, "life2tea.db")
    _db = Database(db_path)
    return _db


__all__ = [
    "Database",
    "get_db",
    "init_db",
]
