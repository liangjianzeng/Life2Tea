"""
openai_proxy.py — Standard OpenAI API Compatible Proxy.

Provides OpenAI-compatible endpoints for Agent access:
  GET  /v1/models          - List available models
  POST /v1/chat/completions - Chat completions (stream or JSON)
  POST /v1/embeddings       - Embeddings (if supported)

Agents can use this with the standard OpenAI SDK:
    from openai import OpenAI
    client = OpenAI(api_key="your-key", base_url="http://localhost:3002/v1")
"""

import json
import time
import httpx
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, AsyncGenerator

from ..routers.models_router import auth_dep
from ..main import get_config_mgr, get_model_registry, get_lifecycle_mgr

router = APIRouter(prefix="/v1", tags=["OpenAI API"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None


class EmbeddingRequest(BaseModel):
    model: str = ""
    input: str | List[str]
    encoding_format: str = "float"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    created: int
    usage: Usage
    choices: List[Dict[str, Any]]


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    model: str
    created: int
    choices: List[Dict[str, Any]]


class ModelResponse(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "life2tea"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: List[ModelResponse]


# ── Helper Functions ─────────────────────────────────────

def _find_model_port(family: str, lifecycle_mgr, cfg_mgr) -> tuple:
    """Find host:port for a model family.
    
    First checks lifecycle manager, then tries default ports.
    Returns (host, port) or raises HTTPException.
    """
    if lifecycle_mgr:
        instances = lifecycle_mgr.list_instances()
        for inst in instances:
            if inst["plugin_name"] == family and inst["status"] == "running":
                return inst["host"], inst["port"]
    
    # If not found, try to get default port from registry
    registry = None
    try:
        from ..main import get_model_registry
        registry = get_model_registry()
        if registry:
            info = registry.get_model(family)
            if info and "default_port" in info:
                return "127.0.0.1", info["default_port"]
    except:
        pass
    
    raise HTTPException(
        status_code=404,
        detail=f"Model family '{family}' not found or not running. Use /v1/models to see available models."
    )


def _build_llama_server_request(req: ChatCompletionRequest) -> dict:
    """Build llama-server compatible request body."""
    return {
        "model": req.model or "default",
        "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "stream": req.stream,
        "stop": req.stop,
        "frequency_penalty": req.frequency_penalty,
        "presence_penalty": req.presence_penalty,
    }


def _transform_llama_response(llama_resp: dict, model_name: str) -> ChatCompletionResponse:
    """Transform llama-server response to OpenAI format."""
    import uuid
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        model=model_name or "unknown",
        created=int(time.time()),
        usage=Usage(
            prompt_tokens=llama_resp.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=llama_resp.get("usage", {}).get("completion_tokens", 0),
            total_tokens=llama_resp.get("usage", {}).get("total_tokens", 0),
        ),
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": llama_resp["choices"][0]["message"]["content"]},
                "finish_reason": llama_resp["choices"][0].get("finish_reason", "stop"),
            }
        ],
    )


# ── Endpoints ────────────────────────────────────────────

@router.get("/models", summary="List available models")
async def list_models(auth=auth_dep):
    """List all available models (OpenAI compatible)."""
    lifecycle_mgr = None
    try:
        from ..main import get_lifecycle_mgr
        lifecycle_mgr = get_lifecycle_mgr()
    except:
        pass

    models = []
    if lifecycle_mgr:
        instances = lifecycle_mgr.list_instances()
        for inst in instances:
            if inst["status"] == "running":
                models.append(ModelResponse(
                    id=inst["plugin_name"],
                    created=int(time.time()),
                    owned_by="llama.cpp",
                ))

    # If no running models, return a default model entry
    if not models:
        models.append(ModelResponse(
            id="default",
            created=int(time.time()),
            owned_by="llama.cpp",
        ))

    return ModelListResponse(data=models)


@router.post("/chat/completions", summary="Chat completions (OpenAI compatible)")
async def chat_completions(
    req: ChatCompletionRequest,
    request: Request,
    lifecycle_mgr=Depends(lambda: None),
):
    """OpenAI-compatible chat completions endpoint.
    
    Routes to the appropriate running model based on the model name.
    """
    # Get model family from request
    model_name = req.model or "default"
    
    # Find the model's port
    host, port = _find_model_port(model_name, lifecycle_mgr, None)
    
    # Build request for llama-server
    llama_req = _build_llama_server_request(req)
    llama_req_url = f"http://{host}:{port}/v1/chat/completions"
    
    headers = {"Content-Type": "application/json"}
    
    if req.stream:
        async def stream_generator():
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", llama_req_url, json=llama_req, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        raise HTTPException(
                            status_code=resp.status_code,
                            detail=f"Model error: {error_body.decode()}"
                        )
                    
                    import uuid
                    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                    created = int(time.time())
                    
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                yield "data: [DONE]\n\n"
                                continue
                            try:
                                data = json.loads(data_str)
                                # Transform to OpenAI format
                                chunk = ChatCompletionChunk(
                                    id=chunk_id,
                                    model=model_name,
                                    created=created,
                                    choices=data.get("choices", []),
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                            except json.JSONDecodeError:
                                continue
                    yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # Non-streaming
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(llama_req_url, json=llama_req, headers=headers)
                
                if resp.status_code != 200:
                    error_body = resp.text
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"Model error: {error_body}"
                    )
                
                llama_resp = resp.json()
                return _transform_llama_response(llama_resp, model_name)
                
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Model request timeout")
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to model at {model_name}"
            )
