"""
chat_router.py — Chat Proxy API.

Endpoints:
  POST /api/chat/completions  (SSE stream or JSON)
  POST /api/chat/completion   (text completion)
  GET  /api/chat/model-info
  GET  /api/chat/health
"""

import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..experts.chat_handler import ChatHandler


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


def _get_handler(request: Request) -> ChatHandler:
    """Get or create ChatHandler, dynamically discovering running model plugins."""
    state = request.app.state
    lifecycle_mgr = state.lifecycle_mgr

    # Find first running model plugin
    instances = lifecycle_mgr.list_instances()
    if instances:
        inst = instances[0]
        host, port = inst["host"], inst["port"]
        # Check if handler needs update
        if (
            not hasattr(state, "chat_handler")
            or state.chat_handler is None
            or state.chat_handler._host != host
            or state.chat_handler._port != port
        ):
            state.chat_handler = ChatHandler(host=host, port=port)
    elif not hasattr(state, "chat_handler") or state.chat_handler is None:
        # No running plugin — use default from config
        cfg = state.config_mgr.get_global()
        host = cfg.get("default_host", "127.0.0.1")
        port = cfg.get("default_port_range", [8080, 8099])[0]
        state.chat_handler = ChatHandler(host=host, port=port)

    return state.chat_handler


@router.post("/completions", summary="OpenAI-style chat completions")
async def chat_completions(body: ChatCompletionBody, request: Request):
    handler = _get_handler(request)
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


@router.post("/completion", summary="Text completion")
async def completion(body: CompletionBody, request: Request):
    handler = _get_handler(request)
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
    handler = _get_handler(request)
    return await handler.get_model_info()


@router.get("/health", summary="Check if chat backend is reachable")
async def chat_health(request: Request):
    handler = _get_handler(request)
    return await handler.health_check()
