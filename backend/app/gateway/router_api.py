"""
router_api.py — OpenAI-compatible API for the Unified Model Gateway.

Replaces the disconnected `proxy_service.py` proxy_router. One entry point for
external consumers (/v1/chat/completions, /v1/completions, /v1/models) with
routing, fallback chains, unified SSE streaming, and optional usage telemetry.
"""

import json
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .providers.base import EndpointStatus, GatewayError, Provider
from .router import GatewayRouter
from .manager import ProviderManager


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = None
    stop: Optional[List[str]] = None
    stream: Optional[bool] = False
    # Arbitrary extra sampling params passed through to the backend
    extra_body: Dict[str, Any] = Field(default_factory=dict)


class CompletionRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False
    extra_body: Dict[str, Any] = Field(default_factory=dict)


class Gateway:
    """Holds the shared manager + router for the gateway API."""

    def __init__(self, manager: ProviderManager):
        self.manager = manager
        self.router = GatewayRouter(manager)
        # Optional telemetry hook: callable(endpoint, usage, error)
        self.on_usage = None
        self.on_error = None


_gateway: Optional[Gateway] = None


def init_gateway(manager: ProviderManager) -> Gateway:
    global _gateway
    _gateway = Gateway(manager)
    return _gateway


def get_gateway() -> Gateway:
    if _gateway is None:
        raise RuntimeError("Gateway not initialized")
    return _gateway


# ── Router ─────────────────────────────────────────────────
gateway_router = APIRouter(tags=["Unified Model Gateway"])


def _error_response(exc: GatewayError, model: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.message,
                "type": exc.error_type,
                "param": None,
                "code": None,
                "model": model,
            }
        },
    )


@gateway_router.get("/health")
async def health(request: Request):
    manager = get_gateway().manager
    return {
        "status": "ok",
        "providers": len(manager.list_endpoints()),
        "running": [
            e.name for e in manager.list_endpoints()
            if e.status == EndpointStatus.RUNNING
        ],
        "gpu": await _gpu_summary(),
    }


async def _gpu_summary() -> Dict[str, Any]:
    from .manager import _get_gpu_memory_mb

    gpu = _get_gpu_memory_mb()
    return {"used_mb": gpu.get("used_mb", 0), "total_mb": gpu.get("total_mb", 0)}


@gateway_router.get("/v1/models")
async def list_models(request: Request):
    gateway = get_gateway()
    data = []
    for e in gateway.manager.list_endpoints():
        data.append(
            {
                "id": e.name,
                "object": "model",
                "created": int(e.load_time) if e.load_time else int(time.time()),
                "owned_by": "life2tea",
                "provider": e.spec.kind.value,
                "status": e.status.value,
            }
        )
    return {"object": "list", "data": data}


@gateway_router.get("/v1/models/{model_name}")
async def get_model(model_name: str, request: Request):
    endpoint = get_gateway().manager.get_endpoint(model_name)
    if not endpoint:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": f"Model '{model_name}' not found", "type": "not_found"}},
        )
    return endpoint.to_dict()


@gateway_router.post("/v1/models/{model_name}/load")
async def load_model(model_name: str, request: Request):
    try:
        endpoint = await get_gateway().manager.start(model_name)
        return {"ok": True, "model": endpoint.to_dict()}
    except GatewayError as e:
        return _error_response(e, model_name)


@gateway_router.post("/v1/models/{model_name}/unload")
async def unload_model(model_name: str, request: Request):
    try:
        endpoint = await get_gateway().manager.stop(model_name)
        return {"ok": True, "model": endpoint.to_dict()}
    except GatewayError as e:
        return _error_response(e, model_name)


@gateway_router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    gateway = get_gateway()
    messages = [m.dict() for m in req.messages]
    chain = gateway.router.route_chain(messages, req.model)

    params = {
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
    }
    if req.top_k is not None:
        params["top_k"] = req.top_k
    if req.stop:
        params["stop"] = req.stop
    params.update(req.extra_body)

    if req.stream:
        return _stream_chat(gateway, chain, messages, params)
    return await _non_stream_chat(gateway, chain, messages, params)


async def _non_stream_chat(gateway: Gateway, chain, messages, params) -> Any:
    last_error: Optional[GatewayError] = None
    for endpoint in chain:
        endpoint.touch()
        provider = Provider(endpoint)
        try:
            _t0 = time.perf_counter()
            result = await provider.chat_completion(messages, stream=False, **params)
            _record_usage(gateway, endpoint, result, latency_seconds=time.perf_counter() - _t0)
            return JSONResponse(content=_openai_shape(result, endpoint.name))
        except GatewayError as e:
            last_error = e
            _record_error(gateway, endpoint, e)
            continue
    return _error_response(last_error or GatewayError("No model available", 503), chain[0].name if chain else "")


_KEEPALIVE_SECONDS = 15


def _stream_chat(gateway: Gateway, chain, messages, params):
    import asyncio

    async def gen():
        last_error: Optional[GatewayError] = None
        for endpoint in chain:
            endpoint.touch()
            provider = Provider(endpoint)
            try:
                async for line in provider.chat_completion_stream(messages, **params):
                    yield line
                # Successful stream — terminate
                yield "data: [DONE]\n\n"
                return
            except GatewayError as e:
                last_error = e
                _record_error(gateway, endpoint, e)
                continue
        # Whole chain failed — emit a single error chunk
        err = last_error or GatewayError("No model available", 503)
        yield f"data: {json.dumps({'error': {'message': err.message, 'type': err.error_type}})}\n\n"
        yield "data: [DONE]\n\n"

    async def with_heartbeat():
        queue: asyncio.Queue = asyncio.Queue()
        stopped = asyncio.Event()

        async def heartbeat():
            try:
                while not stopped.is_set():
                    await asyncio.sleep(_KEEPALIVE_SECONDS)
                    await queue.put(": keep-alive\n\n")
            except asyncio.CancelledError:
                pass

        async def pump():
            try:
                async for chunk in gen():
                    await queue.put(chunk)
            finally:
                await queue.put(None)

        hb_task = asyncio.create_task(heartbeat())
        pump_task = asyncio.create_task(pump())
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            stopped.set()
            hb_task.cancel()
            pump_task.cancel()
            await asyncio.gather(hb_task, pump_task, return_exceptions=True)

    return StreamingResponse(with_heartbeat(), media_type="text/event-stream")


@gateway_router.post("/v1/completions")
async def completions(req: CompletionRequest, request: Request):
    gateway = get_gateway()
    chain = gateway.router.route_chain(model_preference=req.model)
    params = {"max_tokens": req.max_tokens, "temperature": req.temperature}
    params.update(req.extra_body)

    last_error: Optional[GatewayError] = None
    for endpoint in chain:
        endpoint.touch()
        provider = Provider(endpoint)
        try:
            _t0 = time.perf_counter()
            result = await provider.completion(req.prompt, stream=False, **params)
            _record_usage(gateway, endpoint, result, latency_seconds=time.perf_counter() - _t0)
            return JSONResponse(content=_openai_shape(result, endpoint.name))
        except GatewayError as e:
            last_error = e
            _record_error(gateway, endpoint, e)
            continue
    return _error_response(last_error or GatewayError("No model available", 503), chain[0].name if chain else "")


# ── Telemetry helpers ──────────────────────────────────────
def _openai_shape(result: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Guarantee the OpenAI envelope even if the backend omits fields."""
    out = dict(result)
    out.setdefault("object", "chat.completion")
    out.setdefault("model", model)
    out.setdefault("created", int(time.time()))
    out.setdefault("usage", {})
    out.setdefault("choices", [])
    return out


def _record_usage(gateway: Gateway, endpoint, result: Dict[str, Any], latency_seconds: float = 0.0) -> None:
    if not gateway.on_usage:
        return
    usage = result.get("usage") or {}
    completion = usage.get("completion_tokens", 0)
    latency_ms = round(latency_seconds * 1000, 2) if latency_seconds > 0 else 0.0
    tps = round(completion / latency_seconds, 2) if latency_seconds > 0 and completion else 0.0
    try:
        gateway.on_usage(
            endpoint.name,
            {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": completion,
                "total_tokens": usage.get("total_tokens", 0),
                "model": endpoint.name,
                "latency_ms": latency_ms,
                "tps": tps,
            },
        )
    except Exception:
        pass


def _record_error(gateway: Gateway, endpoint, error: GatewayError) -> None:
    if not gateway.on_error:
        return
    try:
        gateway.on_error(endpoint.name, {"error": error.message, "type": error.error_type})
    except Exception:
        pass
