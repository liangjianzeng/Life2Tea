"""
chat_handler.py — Chat Expert Handler

Migrated from LiangLLM/chat_engine.py.
Adapted as an ExpertHandler plugin for the Life2Tea architecture.
Proxies chat/completion requests to any model plugin's HTTP endpoint.
"""

import json
import time
import asyncio
from typing import AsyncGenerator, Optional, List, Dict, Any


class ChatHandler:
    """ExpertHandler that proxies chat requests to a model plugin's HTTP endpoint.

    In Life2Tea architecture, this is registered as an expert that can
    route requests to any loaded model plugin.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self._host = host
        self._port = port
        self._timeout = 300.0

    def update_endpoint(self, host: str, port: int):
        self._host = host
        self._port = port

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        stop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Non-streaming chat completion via HTTPx."""
        import httpx

        body = self._build_body(
            messages, stream=False, max_tokens=max_tokens,
            temperature=temperature, top_p=top_p, top_k=top_k,
            repeat_penalty=repeat_penalty, stop=stop,
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                resp = await client.post(
                    f"http://{self._host}:{self._port}/v1/chat/completions",
                    json=body,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            return {"error": "Request timed out", "timed_out": True}
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500] if e.response.text else ""
            return {"error": f"Backend error: {e.response.status_code}", "detail": detail}
        except Exception as e:
            return {"error": str(e)}

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        stop: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion — yields SSE data chunks + final usage."""
        import httpx

        body = self._build_body(
            messages, stream=True, max_tokens=max_tokens,
            temperature=temperature, top_p=top_p, top_k=top_k,
            repeat_penalty=repeat_penalty, stop=stop,
        )
        start_time = time.time()

        async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
            try:
                async with client.stream(
                    "POST",
                    f"http://{self._host}:{self._port}/v1/chat/completions",
                    json=body,
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[6:].strip()
                        if chunk == "[DONE]":
                            elapsed = time.time() - start_time
                            metrics = json.dumps({
                                "_metrics": {"elapsed_seconds": round(elapsed, 2)}
                            })
                            yield f"data: {metrics}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        yield f"data: {chunk}\n\n"
            except httpx.TimeoutException:
                yield f"data: {json.dumps({'error': 'Request timed out'})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

    async def completion(
        self,
        prompt: str,
        stream: bool = False,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Text completion endpoint."""
        import httpx

        body = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                resp = await client.post(
                    f"http://{self._host}:{self._port}/v1/completions",
                    json=body,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_model_info(self) -> Dict[str, Any]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(
                    f"http://{self._host}:{self._port}/v1/models",
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return {"data": []}

    async def health_check(self) -> Dict[str, Any]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                resp = await client.get(f"http://{self._host}:{self._port}/health")
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "unhealthy", "http_code": resp.status_code}
        except httpx.ConnectError:
            return {"status": "unreachable"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    # ── ExpertHandler interface methods ─────────────────────

    def describe(self) -> Dict[str, Any]:
        """Return tool description for Expert Scheduler."""
        return {
            "name": "chat",
            "description": "Chat with a loaded LLM model plugin",
            "input_schema": {
                "type": "object",
                "properties": {
                    "messages": {"type": "array", "items": {"type": "object"}},
                    "stream": {"type": "boolean", "default": False},
                    "max_tokens": {"type": "integer", "default": 4096},
                    "temperature": {"type": "number", "default": 0.7},
                },
                "required": ["messages"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "choices": {"type": "array"},
                    "usage": {"type": "object"},
                },
            },
        }

    def get_capabilities(self) -> List[str]:
        return ["chat", "completion", "streaming"]

    # ── Internal ─────────────────────────────────────────

    def _build_body(self, messages, stream, **kwargs) -> dict:
        body = {
            "messages": messages,
            "stream": stream,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "top_p": kwargs.get("top_p", 0.9),
            "top_k": kwargs.get("top_k", 40),
            "repeat_penalty": kwargs.get("repeat_penalty", 1.1),
        }
        stop = kwargs.get("stop")
        if stop:
            body["stop"] = stop
        return body
