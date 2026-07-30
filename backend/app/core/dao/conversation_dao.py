"""
conversation_dao.py — Conversation Data Access Object

Provides type-safe database operations for conversations and related entities.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class Conversation:
    """Represents a conversation record."""
    id: str
    title: str = ""
    model_family: Optional[str] = None
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "model_family": self.model_family,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active,
        }


class ConversationDAO:
    """
    Data Access Object for conversations.
    
    Encapsulates all database operations related to conversations,
    providing a clean API for routers and services.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        """
        Initialize with a database connection.
        
        Args:
            db_connection: SQLite connection object
        """
        self._db = db_connection

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the underlying database connection."""
        return self._db

    def create(
        self,
        title: str,
        model_family: Optional[str] = None,
        conversation_id: Optional[str] = None,
        is_active: bool = True,
    ) -> Conversation:
        """
        Create a new conversation.
        
        Args:
            title: Conversation title
            model_family: Associated model family (optional)
            conversation_id: Custom ID (auto-generated if not provided)
            is_active: Whether this is the active conversation
            
        Returns:
            Created Conversation object
        """
        import uuid
        
        conv_id = conversation_id or str(uuid.uuid4())
        now = datetime.now().timestamp()
        
        cursor = self._db.execute(
            """
            INSERT INTO conversations (id, title, model_family, created_at, updated_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conv_id, title, model_family, now, now, 1 if is_active else 0),
        )
        self._db.commit()
        
        return Conversation(
            id=conv_id,
            title=title,
            model_family=model_family,
            created_at=now,
            updated_at=now,
            is_active=is_active,
        )

    def get(self, conversation_id: str) -> Optional[Conversation]:
        """
        Get a conversation by ID.
        
        Args:
            conversation_id: The conversation UUID
            
        Returns:
            Conversation object if found, None otherwise
        """
        cursor = self._db.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_conversation(row)

    def get_by_model(self, model_family: str) -> Optional[Conversation]:
        """
        Get the most recent active conversation for a model.
        
        Args:
            model_family: Model family name
            
        Returns:
            Most recent active conversation for this model
        """
        cursor = self._db.execute(
            """
            SELECT * FROM conversations 
            WHERE model_family = ? AND is_active = 1
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (model_family,),
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_conversation(row)

    def list_all(self, limit: int = 50, offset: int = 0) -> List[Conversation]:
        """
        List all conversations with pagination.
        
        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of Conversation objects
        """
        cursor = self._db.execute(
            """
            SELECT * FROM conversations 
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        
        return [self._row_to_conversation(row) for row in cursor.fetchall()]

    def list_active(self) -> List[Conversation]:
        """
        List all active conversations.
        
        Returns:
            List of active Conversation objects
        """
        cursor = self._db.execute(
            "SELECT * FROM conversations WHERE is_active = 1 ORDER BY updated_at DESC",
        )
        
        return [self._row_to_conversation(row) for row in cursor.fetchall()]

    def update(self, conversation: Conversation) -> bool:
        """
        Update an existing conversation.
        
        Args:
            conversation: Conversation object with updated fields
            
        Returns:
            True if the update affected a row, False otherwise
        """
        now = datetime.now().timestamp()
        
        cursor = self._db.execute(
            """
            UPDATE conversations 
            SET title = ?, model_family = ?, updated_at = ?, is_active = ?
            WHERE id = ?
            """,
            (
                conversation.title,
                conversation.model_family,
                now,
                1 if conversation.is_active else 0,
                conversation.id,
            ),
        )
        self._db.commit()
        
        return cursor.rowcount > 0

    def set_active(self, conversation_id: str) -> bool:
        """
        Set a conversation as active (deactivate others).
        
        Args:
            conversation_id: The conversation to activate
            
        Returns:
            True if successful
        """
        # First deactivate all conversations
        self._db.execute("UPDATE conversations SET is_active = 0")
        
        # Then activate the specified one
        cursor = self._db.execute(
            "UPDATE conversations SET is_active = 1 WHERE id = ?",
            (conversation_id,),
        )
        self._db.commit()
        
        return cursor.rowcount > 0

    def delete(self, conversation_id: str) -> bool:
        """
        Delete a conversation and all its messages.
        
        Args:
            conversation_id: The conversation to delete
            
        Returns:
            True if the deletion affected a row, False otherwise
        """
        # First delete all associated messages (cascading not configured)
        self._db.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        
        cursor = self._db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        self._db.commit()
        
        return cursor.rowcount > 0

    def exists(self, conversation_id: str) -> bool:
        """
        Check if a conversation exists.
        
        Args:
            conversation_id: The conversation UUID
            
        Returns:
            True if the conversation exists, False otherwise
        """
        cursor = self._db.execute(
            "SELECT COUNT(*) FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        return cursor.fetchone()[0] > 0

    def _row_to_conversation(self, row) -> Conversation:
        """Convert a database row to a Conversation object."""
        return Conversation(
            id=row["id"],
            title=row["title"] if row["title"] else "",
            model_family=row["model_family"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            is_active=bool(row["is_active"]),
        )
