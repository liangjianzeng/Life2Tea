"""
manager.py — ProviderManager for the Unified Model Gateway.

Owns model endpoint lifecycle (spawn/kill), port allocation, and resource-aware
eviction. Absorbs the old `DynamicModelManager` (VRAM/LRU) and the subprocess
parts of `PluginLifecycleManager`, but is provider-declarative rather than
plugin-manifest-driven.
"""

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .providers.base import EndpointStatus, GatewayError, ModelEndpoint, ProviderKind, ProviderSpec
from .prober import Prober
from .providers.llamacpp import build_llamacpp_cmd
from .providers.vllm import build_vllm_cmd
from .providers.sglang import build_sglang_cmd

DEFAULT_CONFIG = {
    "providers": {},
    "routing": {
        "code": [],
        "vision": [],
        "ocr": [],
        "math": [],
        "chat": [],
        "fast": [],
        "default": [],
    },
    "resource_budget": {"vram_mb": 0, "ram_mb": 0, "strategy": "evict_lru"},
    "default_port_range": [8080, 8099],
    "default_host": "127.0.0.1",
    "llama_server_exe": "",
    "python": "python",
}


def _get_gpu_memory_mb() -> Dict[str, Any]:
    """Query nvidia-smi once (multi-GPU: report max used / first device)."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            used = total = 0
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 2:
                    try:
                        used += int(parts[0].strip())
                        total += int(parts[1].strip())
                    except ValueError:
                        pass
            return {"used_mb": used, "total_mb": total}
    except Exception:
        pass
    return {"used_mb": 0, "total_mb": 0}


class ProviderManager:
    """Manages model endpoints: discovery, lifecycle, ports, VRAM eviction."""

    def __init__(self, config_path: str, config_mgr=None, prober=None):
        self.config_path = config_path
        self.config_mgr = config_mgr
        self.prober = prober if prober is not None else Prober()
        self._external_ports: set = set()
        self._lock = threading.RLock()
        self._endpoints: Dict[str, ModelEndpoint] = {}
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._load_config()
        self._discover()

    # ── Config ─────────────────────────────────────────────
    def _load_config(self) -> None:
        path = Path(self.config_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(saved)
                self._config = merged
            except Exception as e:
                print(f"[ProviderManager] Failed to load config: {e}", flush=True)

    def _save_config(self) -> None:
        try:
            Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ProviderManager] Failed to save config: {e}", flush=True)

    def get_config(self) -> Dict[str, Any]:
        return self._config

    def update_providers(self, providers: Dict[str, dict]) -> None:
        self._config["providers"] = providers
        self._save_config()
        self._discover()

    def update_routing(self, routing: Dict[str, list]) -> None:
        self._config["routing"] = routing
        self._save_config()

    def remove_provider(self, name: str) -> None:
        """Remove a provider config entry, its endpoint, and routing references."""
        providers = self._config.get("providers", {})
        if name not in providers:
            return
        providers.pop(name)
        self._config["providers"] = providers
        # Kill any running process and drop the stale endpoint from memory
        # (_discover() only adds/updates endpoints, never removes).
        endpoint = self._endpoints.pop(name, None)
        if endpoint is not None and endpoint.pid:
            self._kill_process(endpoint)
        # Clean routing rule references to the removed model.
        routing = self._config.get("routing", {})
        changed = False
        for key, chain in routing.items():
            if isinstance(chain, list) and name in chain:
                routing[key] = [m for m in chain if m != name]
                changed = True
        if changed:
            self._config["routing"] = routing
        self._save_config()

    def get_routing(self) -> Dict[str, list]:
        return self._config.get("routing", {})

    def probe_and_merge(self, prober=None) -> dict:
        """Probe locally-running servers and merge them into the provider config.

        New servers are added (marked auto_discovered), existing entries have
        host/port/model refreshed (manual params preserved), and disappeared
        auto_discovered entries are removed — enabling hot-plug / hot-unplug.
        """
        p = prober if prober is not None else self.prober
        discovered = p.scan() if p is not None else []
        providers = dict(self._config.get("providers", {}))
        external_ports = set()
        added: list = []
        updated: list = []
        removed: list = []
        for d in discovered:
            external_ports.add(d.port)
            if d.name in providers:
                entry = dict(providers[d.name])
                entry["host"] = d.host
                entry["port"] = d.port
                entry["provider"] = d.provider.value
                if d.model_path:
                    entry["model_path"] = d.model_path
                if d.model_name:
                    entry["model_name"] = d.model_name
                # Refresh launch params from the live cmdline so external
                # servers show accurate config (e.g. ctx_size) on every poll.
                entry["params"] = dict(d.params or {})
                entry["auto_discovered"] = True
                providers[d.name] = entry
                updated.append(d.name)
            else:
                entry = {
                    "provider": d.provider.value,
                    "host": d.host,
                    "port": d.port,
                    "params": dict(d.params or {}),
                    "auto_discovered": True,
                }
                if d.model_path:
                    entry["model_path"] = d.model_path
                if d.model_name:
                    entry["model_name"] = d.model_name
                providers[d.name] = entry
                added.append(d.name)
        # hot-unplug: drop auto_discovered entries no longer found
        for name in list(providers.keys()):
            if providers[name].get("auto_discovered") and name not in added and name not in updated:
                providers.pop(name)
                removed.append(name)
        self._external_ports = external_ports
        self._config["providers"] = providers
        self._save_config()
        self._discover()
        # Auto-discovered servers run outside the gateway, so reflect their
        # real live status: mark the endpoint RUNNING with the actual pid
        # instead of the default STOPPED.
        for d in discovered:
            ep = self._endpoints.get(d.name)
            if ep is not None:
                ep.status = EndpointStatus.RUNNING
                ep.pid = d.pid
                ep.external = True
        return {"added": added, "updated": updated, "removed": removed}

    async def _probe_loop(self, interval: float = 30.0) -> None:
        """Background hot-plug loop: periodically probe + merge discovered servers."""
        import asyncio

        while True:
            try:
                await asyncio.to_thread(self.probe_and_merge)
            except Exception as e:
                print(f"[ProviderManager] probe loop error: {e}", flush=True)
            await asyncio.sleep(interval)

    # ── Discovery ───────────────────────────────────────────
    def _discover(self) -> None:
        providers = self._config.get("providers", {})
        default_host = self._config.get("default_host", "127.0.0.1")
        with self._lock:
            for name, data in providers.items():
                try:
                    kind = ProviderKind(data.get("provider", "llamacpp"))
                except ValueError:
                    continue
                spec = ProviderSpec(
                    name=name,
                    kind=kind,
                    host=data.get("host", default_host),
                    port=int(data.get("port", 8080)),
                    model_path=data.get("model_path", ""),
                    model_name=data.get("model_name", ""),
                    launch_cmd=data.get("launch_cmd", []),
                    params=data.get("params", {}),
                    aliases=data.get("aliases", []),
                )
                existing = self._endpoints.get(name)
                if existing:
                    existing.spec = spec
                    # Keep endpoint host/port in sync with spec (used by the
                    # provider client and the API list endpoint).
                    existing.host = spec.host
                    existing.port = spec.port
                    existing.external = data.get("auto_discovered", False)
                else:
                    self._endpoints[name] = ModelEndpoint(
                        name=name, spec=spec, host=spec.host, port=spec.port,
                        external=data.get("auto_discovered", False),
                    )
            # Remove endpoints whose provider config no longer exists
            # (e.g. auto-discovered servers that stopped) — hot-unplug.
            for name in list(self._endpoints.keys()):
                if name not in providers:
                    self._endpoints.pop(name, None)

    def list_endpoints(self) -> List[ModelEndpoint]:
        with self._lock:
            return list(self._endpoints.values())

    def get_endpoint(self, name: str) -> Optional[ModelEndpoint]:
        with self._lock:
            endpoint = self._endpoints.get(name)
            if endpoint is not None:
                return endpoint
            # Alias resolution: a short alias (e.g. "vv4flash") maps to the
            # canonical endpoint name via ProviderSpec.aliases.
            for e in self._endpoints.values():
                aliases = getattr(e.spec, "aliases", []) or []
                if name in aliases:
                    return e
            return None

    # ── Launch command ──────────────────────────────────────
    def _build_cmd(self, spec: ProviderSpec) -> List[str]:
        if spec.launch_cmd:
            return self._expand(spec.launch_cmd)
        cfg = self._config
        if spec.kind == ProviderKind.LLAMACPP:
            server_exe = cfg.get("llama_server_exe", "")
            if not server_exe and self.config_mgr:
                server_exe = self.config_mgr.get_global().get("llama_server_exe", "")
            if not server_exe:
                raise GatewayError("llama_server_exe not configured", status_code=503)
            models_dir = ""
            if self.config_mgr:
                models_dir = self.config_mgr.get_global().get("models_dir", "")
            return build_llamacpp_cmd(spec, server_exe, models_dir)
        if spec.kind == ProviderKind.VLLM:
            return build_vllm_cmd(spec, cfg.get("python", "python"))
        if spec.kind == ProviderKind.SGLANG:
            return build_sglang_cmd(spec, cfg.get("python", "python"))
        raise GatewayError(f"Unknown provider kind: {spec.kind}", status_code=400)

    def _expand(self, cmd: List[str]) -> List[str]:
        models_dir = ""
        if self.config_mgr:
            models_dir = self.config_mgr.get_global().get("models_dir", "")
        return [c.replace("${MODELS_DIR}", models_dir) for c in cmd]

    # ── Lifecycle ───────────────────────────────────────────
    async def start(self, name: str, timeout: float = 180.0) -> ModelEndpoint:
        endpoint = self.get_endpoint(name)
        if not endpoint:
            raise GatewayError(f"Endpoint '{name}' not found", status_code=404)
        if endpoint.status == EndpointStatus.RUNNING:
            endpoint.touch()
            return endpoint

        # Resource-aware: evict LRU if over budget
        self._ensure_budget()

        if endpoint.status != EndpointStatus.RUNNING:
            self._allocate_port(endpoint)

        endpoint.status = EndpointStatus.STARTING
        cmd = self._build_cmd(endpoint.spec)
        log_dir = Path(self.config_path).parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(log_dir / f"{name}.log")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=open(log_file, "w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError as e:
            endpoint.status = EndpointStatus.ERROR
            raise GatewayError(f"Failed to launch '{name}': {e}", status_code=500)
        endpoint.pid = proc.pid
        endpoint.log_file = log_file
        endpoint.status = EndpointStatus.STARTING

        await self._wait_ready(endpoint, timeout)
        endpoint.load_time = time.time()
        endpoint.status = EndpointStatus.RUNNING
        endpoint.touch()
        return endpoint

    async def stop(self, name: str) -> ModelEndpoint:
        endpoint = self.get_endpoint(name)
        if not endpoint:
            raise GatewayError(f"Endpoint '{name}' not found", status_code=404)
        self._kill_process(endpoint)
        endpoint.status = EndpointStatus.STOPPED
        endpoint.pid = 0
        return endpoint

    async def stop_all(self) -> None:
        for endpoint in list(self._endpoints.values()):
            # External servers are not owned by Life2Tea: leave them running.
            if endpoint.status == EndpointStatus.RUNNING and not endpoint.external:
                self._kill_process(endpoint)
                endpoint.status = EndpointStatus.STOPPED
                endpoint.pid = 0

    async def _wait_ready(self, endpoint: ModelEndpoint, timeout: float) -> None:
        import httpx

        url = f"http://{endpoint.host}:{endpoint.port}/health"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if endpoint.pid and self._pid_alive(endpoint.pid) is False:
                break
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return
            except Exception:
                pass
            await asyncio_sleep(0.5)
        # Failed to become ready
        self._kill_process(endpoint)
        endpoint.status = EndpointStatus.ERROR
        raise GatewayError(
            f"Endpoint '{endpoint.name}' failed to start (timed out). See {endpoint.log_file}",
            status_code=500,
        )

    def _pid_alive(self, pid: int) -> Optional[bool]:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _kill_process(self, endpoint: ModelEndpoint) -> None:
        if not endpoint.pid:
            return
        # External hot-plug servers are NOT spawned by Life2Tea, so they must
        # survive Life2Tea's stop/restart. Never terminate them.
        if getattr(endpoint, "external", False):
            return
        try:
            os.kill(endpoint.pid, signal.SIGTERM)
            try:
                os.waitpid(endpoint.pid, 0)
            except (ChildProcessError, OSError):
                pass
        except Exception:
            try:
                os.kill(endpoint.pid, signal.SIGKILL)
            except Exception:
                pass
        endpoint.pid = 0

    # ── Resource budget / LRU eviction ──────────────────────
    def _allocate_port(self, endpoint: ModelEndpoint) -> None:
        lo, hi = self._config.get("default_port_range", [8080, 8099])
        used = {e.port for e in self._endpoints.values() if e.status == EndpointStatus.RUNNING}
        used = used | self._external_ports
        for port in range(lo, hi + 1):
            if port not in used:
                endpoint.port = port
                endpoint.spec.port = port
                return
        raise GatewayError("No available ports", status_code=503)

    def _ensure_budget(self) -> None:
        budget = self._config.get("resource_budget", {})
        max_vram = budget.get("vram_mb", 0)
        if not max_vram:
            return
        gpu = _get_gpu_memory_mb()
        while gpu["used_mb"] >= max_vram:
            evicted = self._evict_lru()
            if not evicted:
                raise GatewayError("VRAM insufficient and no endpoints to evict", status_code=503)
            gpu = _get_gpu_memory_mb()

    def _evict_lru(self) -> Optional[ModelEndpoint]:
        with self._lock:
            running = [
                e for e in self._endpoints.values()
                if e.status == EndpointStatus.RUNNING and not e.external
            ]
            if not running:
                return None
            running.sort(key=lambda e: e.last_used)
            lru = running[0]
        self._kill_process(lru)
        lru.status = EndpointStatus.STOPPED
        lru.pid = 0
        return lru


async def asyncio_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
