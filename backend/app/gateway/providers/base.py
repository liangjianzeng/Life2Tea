"""
base.py — Provider abstraction for the Unified Model Gateway.

A Provider is a thin, generic OpenAI-compatible HTTP client that talks to a
running serving endpoint (llama-server / vLLM / SGLang — all three natively
expose the OpenAI chat/completions + models API). It absorbs the old
`ChatHandler` proxy logic; the lifecycle/VRAM/port concerns moved to
`ProviderManager`; routing moved to `GatewayRouter`.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional


class ProviderKind(str, Enum):
    LLAMACPP = "llamacpp"
    VLLM = "vllm"
    SGLANG = "sglang"


class EndpointStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class GatewayError(Exception):
    """Raised by providers with an OpenAI-style error shape."""

    def __init__(self, message: str, status_code: int = 500, error_type: str = "gateway_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type


@dataclass
class ProviderSpec:
    """Declarative description of a model endpoint (one entry in gateway.json)."""

    name: str
    kind: ProviderKind
    host: str = "127.0.0.1"
    port: int = 8080
    # llamacpp: filesystem path to a GGUF file; vllm/sglang: model name/id
    model_path: str = ""
    model_name: str = ""
    # Optional explicit launch command override (overrides kind-specific builder)
    launch_cmd: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelEndpoint:
    """A live (or desired) model endpoint under gateway management."""

    name: str
    spec: ProviderSpec
    host: str = "127.0.0.1"
    port: int = 8080
    status: EndpointStatus = EndpointStatus.STOPPED
    pid: int = 0
    log_file: str = ""
    last_used: float = field(default_factory=time.time)
    request_count: int = 0
    load_time: float = 0.0

    def touch(self) -> None:
        self.last_used = time.time()
        self.request_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.spec.kind.value,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "pid": self.pid,
            "last_used": self.last_used,
            "request_count": self.request_count,
            "model_path": self.spec.model_path,
            "model_name": self.spec.model_name,
        }


class Provider:
    """Generic OpenAI-compatible HTTP client for a running endpoint."""

    def __init__(self, endpoint: ModelEndpoint, timeout: float = 300.0):
        self.endpoint = endpoint
        self.timeout = timeout
        self._base_url = f"http://{endpoint.host}:{endpoint.port}"

    def _build_chat_body(self, messages, stream, **params) -> dict:
        body: Dict[str, Any] = {
            "model": self.endpoint.name,
            "messages": messages,
            "stream": stream,
        }
        body.update(params)
        return body

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        **params,
    ) -> Dict[str, Any]:
        import httpx

        body = self._build_chat_body(messages, stream=False, **params)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                resp = await client.post(f"{self._base_url}/v1/chat/completions", json=body)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            raise GatewayError("Request timed out", status_code=504, error_type="timeout")
        except httpx.ConnectError:
            raise GatewayError(
                f"Cannot connect to {self.endpoint.name}", status_code=503, error_type="unreachable"
            )
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500] if e.response.text else ""
            raise GatewayError(
                f"Backend error: {e.response.status_code} {detail}",
                status_code=502,
                error_type="backend_error",
            )
        except Exception as e:  # pragma: no cover
            raise GatewayError(str(e), status_code=500)

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        **params,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion — yields raw `data:` SSE lines + `[DONE]`."""
        import httpx

        body = self._build_chat_body(messages, stream=True, **params)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                async with client.stream(
                    "POST", f"{self._base_url}/v1/chat/completions", json=body
                ) as response:
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[6:].strip()
                        if not chunk:
                            continue
                        yield f"data: {chunk}\n\n"
        except httpx.TimeoutException as e:
            raise GatewayError("Request timed out", status_code=504, error_type="timeout") from e
        except httpx.ConnectError as e:
            raise GatewayError(
                f"Cannot connect to {self.endpoint.name}", status_code=503, error_type="unreachable"
            ) from e
        except Exception as e:  # pragma: no cover
            raise GatewayError(str(e), status_code=500) from e

    async def completion(
        self,
        prompt: str,
        stream: bool = False,
        **params,
    ) -> Dict[str, Any]:
        import httpx

        body: Dict[str, Any] = {"prompt": prompt, "stream": stream}
        body.update(params)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                resp = await client.post(f"{self._base_url}/v1/completions", json=body)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            raise GatewayError(str(e), status_code=502) from e

    async def list_models(self) -> List[str]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                resp = await client.get(f"{self._base_url}/v1/models")
                resp.raise_for_status()
                data = resp.json().get("data", [])
                return [m.get("id") or m.get("model", "") for m in data if isinstance(m, dict)]
        except Exception:
            return [self.endpoint.name]

    async def health(self) -> Dict[str, Any]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                resp = await client.get(f"{self._base_url}/health")
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "unhealthy", "http_code": resp.status_code}
        except httpx.ConnectError:
            return {"status": "unreachable"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}
