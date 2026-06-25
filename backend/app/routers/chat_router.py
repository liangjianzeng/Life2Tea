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
from ..core.router import SystemRouter


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
