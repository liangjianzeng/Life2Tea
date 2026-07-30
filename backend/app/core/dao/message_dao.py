"""
message_dao.py — Message Data Access Object

Provides type-safe database operations for chat messages.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class Message:
    """Represents a chat message."""
    id: str
    conversation_id: str
    role: str  # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }


class MessageDAO:
    """
    Data Access Object for messages.
    
    Encapsulates all database operations related to chat messages,
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
        conversation_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
    ) -> Message:
        """
        Create a new message.
        
        Args:
            conversation_id: Parent conversation ID
            role: Message role ("user" or "assistant")
            content: Message content
            message_id: Custom ID (auto-generated if not provided)
            
        Returns:
            Created Message object
        """
        import uuid
        
        msg_id = message_id or str(uuid.uuid4())
        timestamp = datetime.now().timestamp()
        
        cursor = self._db.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (msg_id, conversation_id, role, content, timestamp),
        )
        self._db.commit()
        
        return Message(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=timestamp,
        )

    def get(self, message_id: str) -> Optional[Message]:
        """
        Get a message by ID.
        
        Args:
            message_id: The message UUID
            
        Returns:
            Message object if found, None otherwise
        """
        cursor = self._db.execute(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,),
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_message(row)

    def get_by_conversation(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
        before_timestamp: Optional[float] = None,
    ) -> List[Message]:
        """
        Get messages for a conversation with pagination.
        
        Args:
            conversation_id: Parent conversation ID
            limit: Maximum number of results
            offset: Number of results to skip
            before_timestamp: Only get messages before this timestamp
            
        Returns:
            List of Message objects ordered by timestamp
        """
        if before_timestamp is not None:
            cursor = self._db.execute(
                """
                SELECT * FROM messages 
                WHERE conversation_id = ? AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (conversation_id, before_timestamp, limit, offset),
            )
        else:
            cursor = self._db.execute(
                """
                SELECT * FROM messages 
                WHERE conversation_id = ?
                ORDER BY timestamp
                LIMIT ? OFFSET ?
                """,
                (conversation_id, limit, offset),
            )
        
        return [self._row_to_message(row) for row in cursor.fetchall()]

    def get_recent(
        self,
        conversation_id: str,
        count: int = 10,
    ) -> List[Message]:
        """
        Get the most recent messages from a conversation.
        
        Args:
            conversation_id: Parent conversation ID
            count: Number of messages to retrieve
            
        Returns:
            List of Message objects (most recent first)
        """
        cursor = self._db.execute(
            """
            SELECT * FROM messages 
            WHERE conversation_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (conversation_id, count),
        )
        
        # Reverse to return chronological order
        messages = [self._row_to_message(row) for row in cursor.fetchall()]
        messages.reverse()
        
        return messages

    def update_content(self, message_id: str, new_content: str) -> bool:
        """
        Update a message's content.
        
        Args:
            message_id: The message to update
            new_content: New content text
            
        Returns:
            True if the update affected a row, False otherwise
        """
        cursor = self._db.execute(
            "UPDATE messages SET content = ? WHERE id = ?",
            (new_content, message_id),
        )
        self._db.commit()
        
        return cursor.rowcount > 0

    def delete(self, message_id: str) -> bool:
        """
        Delete a message.
        
        Args:
            message_id: The message to delete
            
        Returns:
            True if the deletion affected a row, False otherwise
        """
        cursor = self._db.execute(
            "DELETE FROM messages WHERE id = ?",
            (message_id,),
        )
        self._db.commit()
        
        return cursor.rowcount > 0

    def delete_by_conversation(self, conversation_id: str) -> int:
        """
        Delete all messages in a conversation.
        
        Args:
            conversation_id: Parent conversation ID
            
        Returns:
            Number of deleted messages
        """
        cursor = self._db.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        self._db.commit()
        
        return cursor.rowcount

    def count_by_conversation(self, conversation_id: str) -> int:
        """
        Count messages in a conversation.
        
        Args:
            conversation_id: Parent conversation ID
            
        Returns:
            Number of messages
        """
        cursor = self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        return cursor.fetchone()[0]

    def _row_to_message(self, row) -> Message:
        """Convert a database row to a Message object."""
        return Message(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            timestamp=row["timestamp"],
        )
