"""
DAO (Data Access Object) module for Life2Tea database operations.

This module provides type-safe, centralized access to the SQLite database,
separating data persistence logic from business logic in routers and services.
"""

from .conversation_dao import ConversationDAO
from .message_dao import MessageDAO

__all__ = ["ConversationDAO", "MessageDAO"]
