"""
prober.py — auto-discovery of running model servers.

Scans live llamacpp / vllm / sglang processes on the local host, resolves each
server's listening port + model, then probes the HTTP API to confirm the
server is alive and to classify its provider kind. The gateway can hot-plug
discovered servers into its provider config without manual gateway.json edits.

The process-scan pattern mirrors `stats_service.get_model_metrics()` but is
generalized to all three provider kinds and adds a /health + /v1/models probe
to confirm liveness and type.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psutil

from .providers.base import ProviderKind

# cmdline markers used to classify a process by provider kind
_PROCESS_MARKERS = {
    ProviderKind.LLAMACPP: ("llama-server", "llama.cpp/build/bin"),
    ProviderKind.VLLM: ("vllm.entrypoints.openai.api_server",),
    ProviderKind.SGLANG: ("sglang.launch_server",),
}

# file extensions stripped when deriving a llamacpp family name
_MODEL_EXTENSIONS = (".gguf", ".bin", ".onnx", ".safetensors")


@dataclass
class DiscoveredEndpoint:
    name: str
    provider: ProviderKind
    host: str
    port: int
    model_path: str = ""
    model_name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    pid: int = 0


class Prober:
    """Discover locally-running model servers and classify them."""

    def __init__(self, default_host: str = "127.0.0.1"):
        self.default_host = default_host

    # ── HTTP helpers (urllib, synchronous) ──
    @staticmethod
    def _http_get_text(url: str, timeout: int = 3) -> Optional[str]:
        import urllib.request

        try:
            req = urllib.request.Request(url, headers={"Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            return None

    @staticmethod
    def _http_get_json(url: str, timeout: int = 3) -> Optional[dict]:
        import json

        text = Prober._http_get_text(url, timeout)
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    # ── Discovery ──
    def scan(self) -> List[DiscoveredEndpoint]:
        """Return discovered endpoints, skipping unresponsive servers."""
        found: List[DiscoveredEndpoint] = []
        seen_ports = set()
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    info = proc.info
                    cmd = info.get("cmdline") or []
                except Exception:
                    continue
                if not cmd:
                    continue
                cmd_str = " ".join(cmd)
                kind = self._classify(cmd_str)
                if kind is None:
                    continue
                pid = info.get("pid")
                port = self._parse_port(cmd, proc)
                if port is None or port in seen_ports:
                    continue
                seen_ports.add(port)

                endpoint = self._probe(port, kind)
                if endpoint is None:
                    # server not responding over HTTP — not ready / not ours
                    continue
                model_path, model_name = self._parse_model(cmd, port)
                endpoint.pid = pid
                endpoint.model_path = model_path
                endpoint.model_name = model_name
                endpoint.params = self._parse_params(cmd)
                endpoint.name = self._make_name(kind, model_path, model_name)
                found.append(endpoint)
        except Exception as e:
            print(f"[Prober] scan error: {e}", flush=True)
        return found

    def _classify(self, cmd_str: str) -> Optional[ProviderKind]:
        for kind, markers in _PROCESS_MARKERS.items():
            for m in markers:
                if m in cmd_str:
                    return kind
        return None

    def _parse_port(self, cmd: List[str], proc) -> Optional[int]:
        for i, a in enumerate(cmd):
            if a in ("--port", "-p", "--grpc-port") and i + 1 < len(cmd):
                try:
                    return int(cmd[i + 1])
                except ValueError:
                    pass
            elif a.startswith("--port="):
                try:
                    return int(a.split("=", 1)[1])
                except ValueError:
                    pass
        # fallback: first LISTEN tcp port
        try:
            for c in proc.net_connections(kind="tcp"):
                if getattr(c, "status", None) == "LISTEN" and c.laddr:
                    return c.laddr.port
        except Exception:
            pass
        return None

    def _probe(self, port: int, kind: ProviderKind) -> Optional[DiscoveredEndpoint]:
        """Confirm liveness and refine provider kind via /health + /v1/models."""
        base = f"http://{self.default_host}:{port}"
        resolved = kind
        health = self._http_get_json(f"{base}/health")
        if health is None:
            # no /health endpoint — likely vllm / sglang (OpenAI-compatible)
            j = self._http_get_json(f"{base}/v1/models")
            if j is None:
                return None
            owned = self._owned_by(j)
            if owned == "vllm":
                resolved = ProviderKind.VLLM
            elif owned == "sglang":
                resolved = ProviderKind.SGLANG
            elif owned == "llamacpp":
                resolved = ProviderKind.LLAMACPP
            # else keep process-based classification
        else:
            status = (health or {}).get("status", "") or ""
            if status.lower() in ("ok", "healthy", "ok"):
                resolved = ProviderKind.LLAMACPP
            # non-ok body: keep process classification
        return DiscoveredEndpoint(
            name="", provider=resolved, host=self.default_host,
            port=port, pid=0,
        )

    @staticmethod
    def _owned_by(j: Optional[dict]) -> str:
        try:
            data = (j or {}).get("data") or []
            if data:
                return str(data[0].get("owned_by", "")).lower()
        except Exception:
            pass
        return ""

    # llama-server cmdline flag -> (spec.params key, is_bool). Keys match
    # build_llamacpp_cmd's _PARAM_TO_FLAG so discovered external servers display
    # the same fields the gateway uses to launch its own.
    _PARAM_FLAGS = {
        "--ctx-size": ("ctx_size", False), "-c": ("ctx_size", False),
        "--n-gpu-layers": ("n_gpu_layers", False), "--gpu-layers": ("n_gpu_layers", False),
        "-ngl": ("n_gpu_layers", False),
        "--mmproj": ("mmproj", False),
        "--threads": ("threads", False), "-t": ("threads", False),
        "--batch-size": ("batch_size", False), "--ubatch-size": ("ubatch_size", False),
        "--parallel": ("parallel", False),
        "--top-k": ("top_k", False), "--top-p": ("top_p", False),
        "--temp": ("temperature", False), "--repeat-penalty": ("repeat_penalty", False),
        "--flash-attn": ("flash_attn", True),
        "--mmap": ("mmap", True), "--mlock": ("mlock", True),
        "--spec-type": ("spec_type", False), "--model-draft": ("model_draft", False),
        "-md": ("model_draft", False),
    }

    @staticmethod
    def _as_num(val: str):
        try:
            return int(val)
        except ValueError:
            try:
                return float(val)
            except ValueError:
                return val

    @classmethod
    def _parse_params(cls, cmd: List[str]) -> Dict[str, Any]:
        """Parse known llama-server flags from a cmdline into a params dict."""
        params: Dict[str, Any] = {}
        i, n = 0, len(cmd)
        while i < n:
            a = cmd[i]
            # --key=value form
            if a.startswith("--") and "=" in a:
                key, _, val = a.partition("=")
                if key in cls._PARAM_FLAGS:
                    pkey, is_bool = cls._PARAM_FLAGS[key]
                    lv = val.lower()
                    if is_bool:
                        params[pkey] = lv in ("on", "true", "1")
                    else:
                        params[pkey] = cls._as_num(val)
                i += 1
                continue
            # --no-xxx boolean negation (e.g. --no-mmap)
            if a.startswith("--no-"):
                key = "--" + a[5:]
                if key in cls._PARAM_FLAGS:
                    params[cls._PARAM_FLAGS[key][0]] = False
                i += 1
                continue
            if a in cls._PARAM_FLAGS:
                pkey, is_bool = cls._PARAM_FLAGS[a]
                if is_bool:
                    if i + 1 < n and cmd[i + 1].lower() in ("on", "off", "true", "false", "1", "0"):
                        params[pkey] = cmd[i + 1].lower() in ("on", "true", "1")
                        i += 2
                    else:
                        params[pkey] = True
                        i += 1
                else:
                    if i + 1 < n:
                        params[pkey] = cls._as_num(cmd[i + 1])
                        i += 2
                    else:
                        i += 1
                continue
            i += 1
        return params

    def _parse_model(self, cmd: List[str], port: int) -> tuple:
        model_path = ""
        model_name = ""
        # prefer /v1/models
        j = self._http_get_json(f"http://{self.default_host}:{port}/v1/models")
        if j:
            models = j.get("models") or j.get("data") or []
            if models:
                m0 = models[0]
                model_path = m0.get("model") or m0.get("model_path") or ""
                model_name = m0.get("name") or m0.get("id") or ""
        if not model_path:
            for i, a in enumerate(cmd):
                if a in ("--model", "-m", "--model-path") and i + 1 < len(cmd):
                    model_path = cmd[i + 1]
                    break
                elif a.startswith("--model="):
                    model_path = a.split("=", 1)[1]
                    break
                elif a.startswith("--model-path="):
                    model_path = a.split("=", 1)[1]
                    break
        return model_path, model_name

    def _make_name(self, kind: ProviderKind, model_path: str, model_name: str) -> str:
        source = model_path or model_name
        if not source:
            return f"auto-{kind.value}"
        if kind == ProviderKind.LLAMACPP:
            base = os.path.basename(source)
            for ext in _MODEL_EXTENSIONS:
                if base.endswith(ext):
                    base = base[: -len(ext)]
                    break
            return base or "llamacpp"
        seg = source.split("/")[-1]
        return seg or source
