"""
logging_service.py — Centralized logging service for model interactions.

Records:
- User authentication (session/user)
- Model selection and parameters
- Generation process (streaming tokens)
- User feedback (ratings, retries)
- Performance metrics (latency, token count)

Logs are stored in database for:
- Analytics (usage patterns)
- Debugging (generation quality)
- Compliance (audit trails)
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import sqlite3
import hashlib


@dataclass
class ModelGenerationLog:
    """Data class for a single model generation log entry."""
    id: str
    user_id: str
    conversation_id: str
    session_id: str
    model_name: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    temperature: Optional[float]
    top_p: Optional[float]
    max_tokens: Optional[int]
    generation_time_ms: float
    message_count: int
    feedback_score: Optional[float]
    feedback_rating: Optional[int]
    retry_count: int
    is_active: bool
    created_at: float
    updated_at: float


@dataclass
class ModelUsageStats:
    """Aggregated statistics for a user or model."""
    user_id: str
    total_generations: int
    total_tokens: int
    avg_generation_time_ms: float
    avg_feedback_score: float
    last_generation_at: Optional[float]
    created_at: float
    updated_at: float


class LoggingService:
    """Centralized logging service for model interactions."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema for logging tables."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Model generation logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_generation_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                provider TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                temperature REAL,
                top_p REAL,
                max_tokens INTEGER,
                generation_time_ms REAL NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 1,
                feedback_score REAL,
                feedback_rating INTEGER,
                retry_count INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # Model usage stats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_usage_stats (
                user_id TEXT PRIMARY KEY,
                total_generations INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                avg_generation_time_ms REAL NOT NULL DEFAULT 0,
                avg_feedback_score REAL NOT NULL DEFAULT 0,
                last_generation_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def log_generation(
        self,
        user_id: str,
        conversation_id: str,
        session_id: str,
        model_name: str,
        provider: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        generation_time_ms: float = 0,
        message_count: int = 1,
        feedback_score: Optional[float] = None,
        feedback_rating: Optional[int] = None,
        retry_count: int = 0,
    ) -> ModelGenerationLog:
        """Log a single model generation event."""
        log_id = hashlib.sha256(
            f"{user_id}{conversation_id}{model_name}{int(time.time())}".encode()
        ).hexdigest()[:16]

        created_at = time.time()
        updated_at = created_at

        # Insert into logs table
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO model_generation_logs
            (id, user_id, conversation_id, session_id, model_name, provider,
             prompt_tokens, completion_tokens, total_tokens,
             temperature, top_p, max_tokens,
             generation_time_ms, message_count,
             feedback_score, feedback_rating, retry_count,
             is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log_id, user_id, conversation_id, session_id, model_name, provider,
            prompt_tokens, completion_tokens, total_tokens,
            temperature, top_p, max_tokens,
            generation_time_ms, message_count,
            feedback_score, feedback_rating, retry_count,
            1, created_at, updated_at
        ))

        conn.commit()
        conn.close()

        # Update stats
        self._update_stats(user_id)

        # Return log object
        return ModelGenerationLog(
            id=log_id,
            user_id=user_id,
            conversation_id=conversation_id,
            session_id=session_id,
            model_name=model_name,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            generation_time_ms=generation_time_ms,
            message_count=message_count,
            feedback_score=feedback_score,
            feedback_rating=feedback_rating,
            retry_count=retry_count,
            is_active=True,
            created_at=created_at,
            updated_at=updated_at,
        )

    def update_generation(
        self,
        log_id: str,
        completion_tokens: int = 0,
        generation_time_ms: float = 0,
        feedback_score: Optional[float] = None,
        feedback_rating: Optional[int] = None,
    ) -> bool:
        """Update an existing generation log with completion data."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        updated_at = time.time()

        cursor.execute("""
            UPDATE model_generation_logs
            SET completion_tokens = COALESCE(?, completion_tokens),
                total_tokens = prompt_tokens + COALESCE(?, completion_tokens),
                generation_time_ms = COALESCE(?, generation_time_ms),
                updated_at = ?
            WHERE id = ?
        """, (completion_tokens, completion_tokens, generation_time_ms, updated_at, log_id))

        affected = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if affected:
            # Get user_id from log (need fresh connection since previous one was closed)
            conn2 = sqlite3.connect(self.db_path)
            conn2.row_factory = sqlite3.Row
            row = conn2.execute("SELECT user_id FROM model_generation_logs WHERE id = ?", (log_id,)).fetchone()
            conn2.close()
            if row:
                user_id = row['user_id']
                self._update_stats(user_id)

        return affected

    def log_feedback(
        self,
        log_id: str,
        rating: int,
        score: Optional[float] = None,
    ) -> bool:
        """Log user feedback for a generation."""
        return self.update_generation(
            log_id=log_id,
            feedback_rating=rating,
            feedback_score=score,
        )

    def _update_stats(self, user_id: str, generation_time_ms: float = 0, feedback_score: Optional[float] = 0.0):
        """Update usage statistics for a user."""
        if feedback_score is None:
            feedback_score = 0.0
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        now = time.time()
        stats = cursor.execute("""
            SELECT total_generations, total_tokens,
                   avg_generation_time_ms, avg_feedback_score,
                   last_generation_at
            FROM model_usage_stats
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if stats:
            # Update existing stats
            cursor.execute("""
                UPDATE model_usage_stats
                SET total_generations = total_generations + 1,
                    total_tokens = total_tokens + ?,
                    avg_generation_time_ms = (
                        (total_generations * avg_generation_time_ms) + ?
                    ) / (total_generations + 1),
                    avg_feedback_score = COALESCE(
                        (avg_feedback_score * total_generations) + ?,
                        ?
                    ) / (total_generations + 1),
                    last_generation_at = ?,
                    updated_at = ?
                WHERE user_id = ?
            """, (0, generation_time_ms, feedback_score, feedback_score, now, now, user_id))
        else:
            # Create new stats
            cursor.execute("""
                INSERT INTO model_usage_stats
                (user_id, total_generations, total_tokens,
                 avg_generation_time_ms, avg_feedback_score,
                 last_generation_at, created_at, updated_at)
                VALUES (?, 1, 0, 0.0, 0.0, ?, ?, ?)
            """, (user_id, now, now, now))

        conn.commit()
        conn.close()

    def get_user_stats(
        self,
        user_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get statistics for a user."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM model_usage_stats
            WHERE user_id = ?
        """, (user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return {}

    def get_user_generations(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get recent generations for a user."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM model_generation_logs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (user_id, limit, offset))

        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return logs


# Global logging service instance
_logging_service: Optional[LoggingService] = None


def get_logging_service() -> LoggingService:
    """Get the global logging service instance."""
    global _logging_service
    if _logging_service is None:
        raise RuntimeError("Logging service not initialized")
    return _logging_service


def init_logging_service(config_dir: str) -> LoggingService:
    """Initialize the global logging service instance."""
    global _logging_service
    db_path = Path(config_dir) / "life2tea.db"
    _logging_service = LoggingService(str(db_path))
    return _logging_service


__all__ = [
    "ModelGenerationLog",
    "ModelUsageStats",
    "LoggingService",
    "get_logging_service",
    "init_logging_service",
]
