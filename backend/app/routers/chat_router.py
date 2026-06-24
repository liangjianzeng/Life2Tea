"""
chat_router.py — Chat Proxy API.

Endpoints:
  POST /api/chat/completions  (SSE stream or JSON)
  POST /api/chat/completion   (text completion)
  GET  /api/chat/model-info
  GET  /api/chat/health
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..main import get_config_mgr, get_lifecycle_mgr
from ..experts.chat_handler import ChatHandler


router = APIRouter()

# Global chat handler (reused across requests)
_chat_handler: Optional[ChatHandler] = None
_chat_lock = None  # initialized in startup


def _get_handler() -> ChatHandler:
    global _chat_handler
    if _chat_handler is None:
        cfg = get_config_mgr().get_global()
        host = cfg.get("default_host", "127.0.0.1")
        port = cfg.get("default_port_range", [8080, 8099])[0]
        _chat_handler = ChatHandler(host=host, port=port)
    return _chat_handler


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


@router.post("/completions")
async def chat_completions(body: ChatCompletionBody):
    handler = _get_handler()
    messages = [m.dict() for m in body.messages]

    if body.stream:
        async def gen():
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
        return StreamingResponse(gen(), media_type="text/event-stream")

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
    return result


@router.post("/completion")
async def completion(body: CompletionBody):
    handler = _get_handler()
    result = await handler.completion(
        prompt=body.prompt,
        stream=body.stream,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/model-info")
async def get_model_info():
    handler = _get_handler()
    return await handler.get_model_info()


@router.get("/health")
async def chat_health():
    handler = _get_handler()
    return await handler.health_check()
