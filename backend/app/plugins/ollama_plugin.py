"""
ollama_plugin.py — Ollama Model Plugin for Life2Tea.

Implements IModelPlugin interface to integrate Ollama as a model backend.
Supports:
  - Connecting to an existing Ollama server (default port 11434)
  - Auto-starting Ollama if not running
  - Streaming and non-streaming inference via /api/chat/completions
  - Model pull on demand

Usage as a plugin:
    from app.plugins.ollama_plugin import OllamaPlugin
    plugin = OllamaPlugin(manifest)
    plugin.load()
    result = await plugin.infer(messages, stream=False)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from .base import IModelPlugin, PluginHealth


# Default Ollama server address
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434
HEALTH_ENDPOINT = "/api/tags"
CHAT_ENDPOINT = "/api/chat"
PULL_ENDPOINT = "/api/pull"

# Timeout for HTTP requests to Ollama (seconds)
REQUEST_TIMEOUT = 600.0


class OllamaPlugin(IModelPlugin):
    """Ollama model plugin — wraps an Ollama server as a Life2Tea model plugin.

    The plugin connects to an existing Ollama server (or starts one if not running).
    All inference is forwarded via the Ollama HTTP API in OpenAI-compatible format.
    """

    def __init__(self, manifest) -> None:
        super().__init__(manifest)
        self._host = DEFAULT_HOST
        self._port = DEFAULT_PORT
        self._server_proc: Optional[subprocess.Popen] = None
        self._loaded = False
        self._model_name: str = ""

    # ── IModelPlugin interface ────────────────────────────────

    @property
    def endpoint(self) -> Tuple[str, int]:
        """Return (host, port) of the Ollama server."""
        return (self._host, self._port)

    async def load(
        self, config: Optional[Dict[str, Any]] = None
    ) -> None:
        """Load the plugin — connect to or start Ollama server.

        Args:
            config: Plugin configuration with optional keys:
                - host: Ollama server host (default 127.0.0.1)
                - port: Ollama server port (default 11434)
                - model: Model name to pull/load (e.g. "qwen3.6:35b")
        """
        if self._loaded:
            return

        cfg = config or {}
        self._host = cfg.get("host", DEFAULT_HOST)
        self._port = int(cfg.get("port", DEFAULT_PORT))
        self._model_name = cfg.get("model", "")

        # Try to connect to existing Ollama server
        if not await self._check_server():
            print(
                f"[OllamaPlugin:{self.name}] Ollama not running at "
                f"{self._host}:{self._port}, attempting to start...",
                flush=True,
            )
            await self._start_ollama()

        # Pull model if specified and not already present
        if self._model_name:
            await self._ensure_model(self._model_name)

        self._loaded = True
        print(
            f"[OllamaPlugin:{self.name}] Loaded successfully "
            f"at {self._host}:{self._port}",
            flush=True,
        )

    async def unload(self) -> None:
        """Unload the plugin — stop Ollama server if we started it."""
        if not self._loaded:
            return

        # Only kill our own subprocess, not a system-wide Ollama
        if self._server_proc is not None and self._server_proc.poll() is None:
            try:
                print(
                    f"[OllamaPlugin:{self.name}] Stopping Ollama server (PID={self._server_proc.pid})",
                    flush=True,
                )
                self._server_proc.terminate()
                try:
                    self._server_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._server_proc.kill()
            except Exception as e:
                print(
                    f"[OllamaPlugin:{self.name}] Error stopping Ollama: {e}",
                    flush=True,
                )

        self._loaded = False
        self._server_proc = None
        print(f"[OllamaPlugin:{self.name}] Unloaded", flush=True)

    def health(self) -> PluginHealth:
        """Probe liveness of the Ollama server."""
        try:
            url = f"http://{self._host}:{self._port}{HEALTH_ENDPOINT}"
            req = urllib.request.urlopen(url, timeout=5)
            if req.status == 200:
                data = json.loads(req.read().decode("utf-8"))
                model_count = len(data.get("models", []))
                return PluginHealth(
                    healthy=True,
                    detail=f"Ollama running with {model_count} models loaded",
                    extra={"model_count": model_count},
                )
        except Exception as e:
            pass

        return PluginHealth(
            healthy=False,
            detail="Ollama server not reachable",
        )

    async def infer(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Run inference via Ollama /api/chat endpoint.

        Args:
            messages: Chat messages in OpenAI format.
            stream: If True, return async generator of SSE chunks.
            **kwargs: Sampling params (temperature, max_tokens, etc.)

        Returns:
            Non-streaming: dict with OpenAI-compatible response
            Streaming: async generator yielding SSE data strings
        """
        if not self._loaded:
            raise RuntimeError("Ollama plugin not loaded")

        # Determine model name
        model = kwargs.pop("model", self._model_name or "qwen3.6")

        # Build Ollama-compatible request body
        body = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        # Map sampling params to Ollama format
        if "temperature" in kwargs:
            body["options"] = body.get("options", {})
            body["options"]["temperature"] = kwargs.pop("temperature")
        if "top_p" in kwargs:
            body.setdefault("options", {})["top_p"] = kwargs.pop("top_p")
        if "top_k" in kwargs:
            body.setdefault("options", {})["top_k"] = kwargs.pop("top_k")
        if "repeat_penalty" in kwargs:
            body.setdefault("options", {})["repeat_penalty"] = kwargs.pop("repeat_penalty")

        url = f"http://{self._host}:{self._port}{CHAT_ENDPOINT}"

        if stream:
            return self._stream_infer(url, body)
        else:
            return await self._chat_completion(url, body)

    # ── Internal helpers ──────────────────────────────────────

    async def _check_server(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            url = f"http://{self._host}:{self._port}{HEALTH_ENDPOINT}"
            req = urllib.request.urlopen(url, timeout=3)
            return req.status == 200
        except Exception:
            return False

    async def _start_ollama(self) -> bool:
        """Start Ollama server as a subprocess."""
        try:
            # Find ollama binary
            ollama_exe = shutil.which("ollama") or "ollama"

            proc_env = os.environ.copy()
            proc_env["OLLAMA_HOST"] = f"{self._host}:{self._port}"

            log_file = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "log",
                f"plugin_ollama_{self._port}.log"
            )
            os.makedirs(os.path.dirname(log_file), exist_ok=True)

            self._server_proc = subprocess.Popen(
                [ollama_exe, "serve"],
                stdout=open(log_file, "a"),
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=proc_env,
                start_new_session=True,
            )

            # Wait for server to be ready (up to 30s)
            for _ in range(30):
                time.sleep(1)
                if await self._check_server():
                    print(
                        f"[OllamaPlugin:{self.name}] Ollama started on "
                        f"{self._host}:{self._port} (PID={self._server_proc.pid})",
                        flush=True,
                    )
                    return True

            # Timeout — process might still be starting
            if self._server_proc.poll() is not None:
                print(
                    f"[OllamaPlugin:{self.name}] Ollama exited with code "
                    f"{self._server_proc.returncode}",
                    flush=True,
                )
                return False

            print(
                f"[OllamaPlugin:{self.name}] Warning: Ollama not ready after 30s",
                flush=True,
            )
            return True  # Process is running, might just be slow

        except FileNotFoundError:
            print(
                f"[OllamaPlugin:{self.name}] ollama binary not found. "
                f"Please install Ollama or set OLLAMA_HOME.",
                flush=True,
            )
            return False
        except Exception as e:
            print(f"[OllamaPlugin:{self.name}] Failed to start Ollama: {e}", flush=True)
            return False

    async def _ensure_model(self, model_name: str) -> bool:
        """Pull or verify a model exists on the Ollama server."""
        try:
            # Check if model already exists
            url = f"http://{self._host}:{self._port}{HEALTH_ENDPOINT}"
            req = urllib.request.urlopen(url, timeout=5)
            data = json.loads(req.read().decode("utf-8"))
            existing = [m["name"] for m in data.get("models", [])]

            if model_name in existing:
                print(f"[OllamaPlugin:{self.name}] Model {model_name} already loaded", flush=True)
                return True

            # Pull the model
            print(
                f"[OllamaPlugin:{self.name}] Pulling model {model_name}...",
                flush=True,
            )
            pull_url = f"http://{self._host}:{self._port}{PULL_ENDPOINT}"
            payload = json.dumps({"name": model_name}).encode("utf-8")

            req = urllib.request.Request(
                pull_url, data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                for line in resp.read().decode("utf-8").split("\n"):
                    if line.strip():
                        chunk = json.loads(line)
                        status = chunk.get("status", "")
                        if "digest" in chunk:
                            pct = chunk.get("completed", 0) / max(chunk.get("total", 1), 1) * 100
                            print(f"[OllamaPlugin:{self.name}]   {status}: {pct:.0f}%", flush=True)
                        else:
                            print(f"[OllamaPlugin:{self.name}]   {status}", flush=True)

            print(
                f"[OllamaPlugin:{self.name}] Model {model_name} pulled successfully",
                flush=True,
            )
            return True

        except Exception as e:
            print(f"[OllamaPlugin:{self.name}] Failed to ensure model {model_name}: {e}", flush=True)
            return False

    async def _chat_completion(self, url: str, body: dict) -> Dict[str, Any]:
        """Non-streaming chat completion via Ollama API."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            return {"error": "Ollama request timed out", "timed_out": True}
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500] if e.response.text else ""
            return {"error": f"Ollama error {e.response.status_code}", "detail": detail}
        except Exception as e:
            return {"error": str(e)}

    async def _stream_infer(self, url: str, body: dict) -> AsyncGenerator[str, None]:
        """Streaming inference — yields SSE data chunks."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                async with client.stream("POST", url, json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        yield f"data: {line}\n\n"

            # Send final [DONE] event
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_msg = json.dumps({"error": str(e)})
            yield f"data: {error_msg}\n\n"
            yield "data: [DONE]\n\n"


# ── Utility: check if Ollama is available on the system ───

def is_ollama_available() -> bool:
    """Check if ollama binary exists and server can be reached."""
    try:
        result = subprocess.run(
            ["which", "ollama"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return False

        # Check if server is running
        url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}{HEALTH_ENDPOINT}"
        req = urllib.request.urlopen(url, timeout=3)
        return req.status == 200
    except Exception:
        return False


def get_ollama_models() -> List[str]:
    """Get list of models available on the Ollama server."""
    try:
        url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}{HEALTH_ENDPOINT}"
        req = urllib.request.urlopen(url, timeout=5)
        data = json.loads(req.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


__all__ = ["OllamaPlugin", "is_ollama_available", "get_ollama_models"]
