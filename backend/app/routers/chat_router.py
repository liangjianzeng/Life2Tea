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

from ..gateway.providers.base import EndpointStatus, GatewayError, Provider


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


class ConversationUpdateBody(BaseModel):
    title: Optional[str] = None
    model_family: Optional[str] = None


class MessageBody(BaseModel):
    conversation_id: str
    role: str
    content: str


def _get_gateway(request: Request):
    """Get the shared gateway (manager + router) from app.state."""
    return request.app.state.gateway


async def _get_endpoint(request: Request, messages: List[Dict[str, str]], model_pref: Optional[str] = None):
    """Route to an endpoint via the GatewayRouter; auto-start if stopped."""
    gateway = _get_gateway(request)
    endpoint = gateway.router.select(messages=messages, model_preference=model_pref)
    if not endpoint:
        raise HTTPException(status_code=503, detail="No model endpoints configured")
    if endpoint.status != EndpointStatus.RUNNING:
        try:
            endpoint = await gateway.manager.start(endpoint.name)
        except GatewayError as e:
            raise HTTPException(status_code=503, detail=e.message)
    return endpoint


@router.post("/completions", summary="OpenAI-style chat completions")
async def chat_completions(body: ChatCompletionBody, request: Request):
    messages = [m.dict() for m in body.messages]
    gateway = _get_gateway(request)

    params = {
        "max_tokens": body.max_tokens,
        "temperature": body.temperature,
        "top_p": body.top_p,
        "top_k": body.top_k,
        "repeat_penalty": body.repeat_penalty,
    }
    if body.stop:
        params["stop"] = body.stop

    # Build fallback chain via the gateway router
    chain = gateway.router.route_chain(messages=messages, model_preference=body.model)

    if body.stream:
        return StreamingResponse(
            _stream_gen(request, gateway, chain, messages, params),
            media_type="text/event-stream",
        )

    last_error = None
    for endpoint in chain:
        endpoint.touch()
        provider = Provider(endpoint)
        try:
            result = await provider.chat_completion(messages, stream=False, **params)
            _log_generation(request, messages, body, result)
            return result
        except GatewayError as e:
            last_error = e
            continue
    raise HTTPException(status_code=502, detail=last_error.message if last_error else "No model available")


async def _stream_gen(request, gateway, chain, messages, params):
    last_error = None
    for endpoint in chain:
        endpoint.touch()
        provider = Provider(endpoint)
        try:
            async for chunk in provider.chat_completion_stream(messages, **params):
                yield chunk
            yield "data: [DONE]\n\n"
            _log_generation(request, messages, None, None)
            return
        except GatewayError as e:
            last_error = e
            continue
    err = last_error
    import json
    yield f"data: {json.dumps({'error': {'message': err.message if err else 'No model available', 'type': err.error_type if err else 'unavailable'}})}\n\n"
    yield "data: [DONE]\n\n"


def _log_generation(request, messages, body, result):
    """Persist generation log with real usage tokens (Phase 3 telemetry)."""
    if not hasattr(request.app.state, "logging_service"):
        return
    from ..core.logging_service import get_logging_service

    logging_service = get_logging_service()
    try:
        usage = (result or {}).get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", len(messages))
        completion_tokens = usage.get("completion_tokens", 0)
        current_user = getattr(request.state, "current_user", None)
        user_id = current_user.id if current_user else "anonymous"
        conv_id = getattr(request.state, "conversation_id", "anonymous")
        log = logging_service.log_generation(
            user_id=user_id,
            conversation_id=conv_id,
            session_id=getattr(request.state, "session_id", "anonymous"),
            model_name=body.model if body else "unknown",
            provider="gateway",
            temperature=body.temperature if body else 0.7,
            top_p=body.top_p if body else 0.9,
            max_tokens=body.max_tokens if body else 4096,
            retry_count=0,
        )
        log_id = getattr(log, "id", None)
        if log_id:
            logging_service.update_generation(
                log_id=log_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
    except Exception:
        pass


@router.post("/completion", summary="Text completion")
async def completion(body: CompletionBody, request: Request):
    fake_messages = [{"role": "user", "content": body.prompt}]
    endpoint = await _get_endpoint(request, fake_messages)
    provider = Provider(endpoint)
    try:
        result = await provider.completion(
            prompt=body.prompt,
            stream=body.stream,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        )
    except GatewayError as e:
        raise HTTPException(status_code=502, detail=e.message)
    return result


@router.get("/model-info", summary="Get loaded model info from running backend")
async def get_model_info(request: Request):
    endpoint = await _get_endpoint(request, [{"role": "user", "content": "hi"}])
    provider = Provider(endpoint)
    return await provider.list_models()


@router.get("/health", summary="Check if chat backend is reachable")
async def chat_health(request: Request):
    endpoint = await _get_endpoint(request, [{"role": "user", "content": "hi"}])
    provider = Provider(endpoint)
    return await provider.health()


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


@router.put("/conversation/{conversation_id}", summary="Update conversation (title / model)")
async def update_conversation(conversation_id: str, body: ConversationUpdateBody, request: Request):
    from ..core.database import _db
    db = _db.get_connection()
    try:
        now = datetime.now().timestamp()
        if body.title is not None and body.model_family is not None:
            db.execute(
                "UPDATE conversations SET title = ?, model_family = ?, updated_at = ? WHERE id = ?",
                (body.title, body.model_family, now, conversation_id),
            )
        elif body.title is not None:
            db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (body.title, now, conversation_id),
            )
        else:
            db.execute(
                "UPDATE conversations SET model_family = ?, updated_at = ? WHERE id = ?",
                (body.model_family, now, conversation_id),
            )
        db.commit()
        return {"ok": True, "conversation_id": conversation_id}
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


@router.delete("/conversation/{conversation_id}", summary="Delete a conversation and its messages")
async def delete_conversation(conversation_id: str, request: Request):
    from ..core.database import _db
    db = _db.get_connection()
    try:
        # Delete all messages in the conversation first
        db.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        )
        # Delete the conversation itself
        cursor = db.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"ok": True}
    finally:
        db.close()
