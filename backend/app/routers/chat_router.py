"""
chat_router.py — Chat Proxy API.

Endpoints:
  POST /api/chat/completions  (SSE stream or JSON)
  POST /api/chat/completion   (text completion)
  GET  /api/chat/model-info
  GET  /api/chat/health
  GET  /api/chat/conversations  (list conversations)
  GET  /api/chat/conversation/{id}  (get conversation)
  POST /api/chat/conversation  (create conversation)
  POST /api/chat/message  (save message)
"""

import json
import uuid
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..experts.chat_handler import ChatHandler
from ..core.routing import SystemRouter


router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionBody(BaseModel):
    messages: List[ChatMessage]
    stream: bool = False
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    stop: Optional[List[str]] = None
    model: Optional[str] = None  # plugin name to route to


class CompletionBody(BaseModel):
    prompt: str
    stream: bool = False
    max_tokens: int = 512
    temperature: float = 0.7


class ConversationCreateBody(BaseModel):
    title: Optional[str] = "New Conversation"
    model_family: Optional[str] = None


class MessageBody(BaseModel):
    conversation_id: str
    role: str
    content: str


def _get_router(request: Request) -> SystemRouter:
    """Get SystemRouter instance from app.state."""
    return request.app.state.system_router


def _get_running_plugins(request: Request) -> list:
    """Get list of running model plugin names."""
    state = request.app.state
    lifecycle_mgr = state.lifecycle_mgr
    instances = lifecycle_mgr.list_instances()
    return [inst["plugin_name"] for inst in instances if inst["status"] == "running"]


def _get_host_port_for_plugin(request: Request, plugin_name: str) -> tuple:
    """Find host:port for a running plugin."""
    state = request.app.state
    lifecycle_mgr = state.lifecycle_mgr
    instances = lifecycle_mgr.list_instances()
    for inst in instances:
        if inst["plugin_name"] == plugin_name and inst["status"] == "running":
            return inst["host"], inst["port"]
    # Plugin not running — return defaults
    return "127.0.0.1", 8080


def _get_handler(request: Request, messages: List[Dict[str, str]], model_pref: Optional[str] = None) -> ChatHandler:
    """Get ChatHandler, using SystemRouter to select the best model plugin."""
    state = request.app.state
    router = _get_router(request)

    # Use router to select model
    running = _get_running_plugins(request)
    selected_plugin, _, _ = router.select_model(
        messages=messages,
        model_preference=model_pref,
        running_plugins=running,
    )

    host, port = _get_host_port_for_plugin(request, selected_plugin)

    # Check if handler needs update
    if (
        not hasattr(state, "chat_handler")
        or state.chat_handler is None
        or state.chat_handler._host != host
        or state.chat_handler._port != port
    ):
        state.chat_handler = ChatHandler(host=host, port=port)

    return state.chat_handler


@router.post("/completions", summary="OpenAI-style chat completions")
async def chat_completions(body: ChatCompletionBody, request: Request):
    messages = [m.dict() for m in body.messages]
    handler = _get_handler(request, messages, model_pref=body.model)

    # Log generation start
    if hasattr(request.app.state, "logging_service"):
        from ..core.logging_service import get_logging_service
        logging_service = get_logging_service()

        # Try to get user_id from request state or use default
        current_user = getattr(request.state, "current_user", None)
        user_id = current_user.id if current_user else "anonymous"

        session_id = getattr(request.state, "session_id", None)
        if not session_id:
            session_id = "anonymous"

        # Get conversation_id from messages or create one
        conversation_id = getattr(request.state, "conversation_id", None)
        if not conversation_id:
            # Try to get from last user message or create new
            for msg in reversed(messages):
                if msg["role"] == "user":
                    conversation_id = getattr(request.state, "conversation_id", None)
                    break
            if not conversation_id:
                from datetime import datetime
                conv_id = str(uuid.uuid4())
                conversation_id = conv_id

        # Log generation start
        log = logging_service.log_generation(
            user_id=user_id,
            conversation_id=conversation_id,
            session_id=session_id,
            model_name=body.model or "unknown",
            provider="llama.cpp",
            temperature=body.temperature,
            top_p=body.top_p,
            max_tokens=body.max_tokens,
            retry_count=0,
        )
        request.state.generation_log_id = log.id

    if body.stream:
        async def gen():
            start_time = time.time()

            # Log streaming start
            if hasattr(request.state, "generation_log_id"):
                from ..core.logging_service import get_logging_service
                logging_service = get_logging_service()
                try:
                    logging_service.update_generation(
                        log_id=request.state.generation_log_id,
                        prompt_tokens=len(messages),  # Approximate
                    )
                except:
                    pass

            async for chunk in handler.chat_completion_stream(
                messages=messages,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
                top_p=body.top_p,
                top_k=body.top_k,
                repeat_penalty=body.repeat_penalty,
                stop=body.stop,
            ):
                yield chunk

            # Log streaming completion
            if hasattr(request.state, "generation_log_id"):
                from ..core.logging_service import get_logging_service
                logging_service = get_logging_service()
                try:
                    elapsed_ms = (time.time() - start_time) * 1000
                    logging_service.update_generation(
                        log_id=request.state.generation_log_id,
                        generation_time_ms=elapsed_ms,
                        completion_tokens=0,  # Will be counted from actual response
                    )
                except:
                    pass
        return StreamingResponse(gen(), media_type="text/event-stream")

    start_time = time.time()
    result = await handler.chat_completion(
        messages=messages,
        stream=False,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        top_k=body.top_k,
        repeat_penalty=body.repeat_penalty,
        stop=body.stop,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    # Log completion
    if hasattr(request.app.state, "logging_service"):
        from ..core.logging_service import get_logging_service
        logging_service = get_logging_service()
        try:
            elapsed_ms = (time.time() - start_time) * 1000

            # Estimate completion tokens from response length
            completion_tokens = len(result.get("content", ""))

            logging_service.update_generation(
                log_id=request.state.generation_log_id,
                completion_tokens=completion_tokens,
                generation_time_ms=elapsed_ms,
            )
        except:
            pass

    return result


@router.post("/completion", summary="Text completion")
async def completion(body: CompletionBody, request: Request):
    # Build a fake messages list for the router
    fake_messages = [{"role": "user", "content": body.prompt}]
    handler = _get_handler(request, fake_messages)
    result = await handler.completion(
        prompt=body.prompt,
        stream=body.stream,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/model-info", summary="Get loaded model info from running backend")
async def get_model_info(request: Request):
    # Use default chat messages for routing
    handler = _get_handler(request, [{"role": "user", "content": "hi"}])
    return await handler.get_model_info()


@router.get("/health", summary="Check if chat backend is reachable")
async def chat_health(request: Request):
    handler = _get_handler(request, [{"role": "user", "content": "hi"}])
    return await handler.health_check()


@router.get("/conversations", summary="List all conversations")
async def list_conversations(request: Request):
    from ..core.database import _db
    db = _db.get_connection()
    try:
        cursor = db.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC"
        )
        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                "id": row["id"],
                "title": row["title"],
                "model_family": row["model_family"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "is_active": bool(row["is_active"]),
            })
        return {"conversations": conversations}
    finally:
        db.close()


@router.get("/conversation/{conversation_id}", summary="Get conversation with messages")
async def get_conversation(conversation_id: str, request: Request):
    from ..core.database import _db
    db = _db.get_connection()
    try:
        cursor = db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        )
        conv = cursor.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        cursor = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp",
            (conversation_id,)
        )
        messages = []
        for row in cursor.fetchall():
            messages.append({
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["timestamp"],
            })

        return {
            "conversation": {
                "id": conv["id"],
                "title": conv["title"],
                "model_family": conv["model_family"],
                "created_at": conv["created_at"],
                "updated_at": conv["updated_at"],
            },
            "messages": messages,
        }
    finally:
        db.close()


@router.post("/conversation", summary="Create new conversation")
async def create_conversation(body: ConversationCreateBody, request: Request):
    from ..core.database import _db
    db = _db.get_connection()
    try:
        now = datetime.now().timestamp()
        conv_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO conversations (id, title, model_family, created_at, updated_at, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (conv_id, body.title, body.model_family, now, now)
        )
        db.commit()
        return {"conversation": {"id": conv_id, "title": body.title, "model_family": body.model_family}}
    finally:
        db.close()


@router.post("/message", summary="Save a message to conversation")
async def save_message(body: MessageBody, request: Request):
    from ..core.database import _db
    db = _db.get_connection()
    try:
        msg_id = str(uuid.uuid4())
        now = datetime.now().timestamp()
        db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (msg_id, body.conversation_id, body.role, body.content, now)
        )
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, body.conversation_id)
        )
        db.commit()
        return {"message_id": msg_id, "ok": True}
    finally:
        db.close()
