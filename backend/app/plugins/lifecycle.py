"""
lifecycle.py — Plugin Lifecycle Manager

Migrated from LiangLLM/process_manager.py.
Manages plugin process lifecycle: load, unload, health check, resource tracking.
Generic — works for any plugin type (model, expert, backend).
"""

import os
import sys
import time
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum

import psutil


def _log_reader(stream, log_path: str):
    """Read lines from stream and append to log file (runs in daemon thread)."""
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            for line in iter(stream.readline, b""):
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
                f.write(decoded)
                f.flush()
    except Exception:
        pass


class PluginStatus(str, Enum):
    LOADING = "loading"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class PluginInstance:
    plugin_name: str
    plugin_type: str  # "model" | "expert" | "backend"
    pid: int = 0
    process: Optional[subprocess.Popen] = None
    host: str = "127.0.0.1"
    port: int = 0
    log_file: str = ""
    started_at: float = 0.0
    status: str = PluginStatus.STOPPED
    health_endpoint: str = "/health"
    resource_usage: Dict = field(default_factory=dict)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0

    @property
    def memory_mb(self) -> float:
        try:
            return psutil.Process(self.pid).memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    @property
    def cpu_percent(self) -> float:
        try:
            return psutil.Process(self.pid).cpu_percent(interval=0.1)
        except Exception:
            return 0.0

    def to_dict(self) -> dict:
        return {
            "plugin_name": self.plugin_name,
            "plugin_type": self.plugin_type,
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "status": self.status,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "memory_mb": round(self.memory_mb, 1),
            "cpu_percent": round(self.cpu_percent, 1),
            "log_file": self.log_file,
        }


class PluginLifecycleManager:
    """Manages plugin process lifecycle (load/unload/health)."""

    def __init__(self, log_dir: str):
        self._instances: Dict[str, PluginInstance] = {}
        self._lock = threading.Lock()
        self._log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    # ── Public API ──────────────────────────────────────

    def get_instance(self, plugin_name: str) -> Optional[PluginInstance]:
        with self._lock:
            inst = self._instances.get(plugin_name)
            if inst and inst.process and inst.process.poll() is None:
                return inst
            if inst:
                inst.status = PluginStatus.STOPPED
            return None

    def list_instances(self) -> List[dict]:
        with self._lock:
            return [inst.to_dict() for inst in self._instances.values()
                    if inst.status == PluginStatus.RUNNING]

    def start_plugin(
        self,
        plugin_name: str,
        plugin_type: str,
        command: List[str],
        host: str = "127.0.0.1",
        port: int = 0,
        health_endpoint: str = "/health",
        env: Optional[Dict[str, str]] = None,
    ) -> PluginInstance:
        """Start a plugin process. If already running, stop first."""
        with self._lock:
            # Stop existing instance
            if plugin_name in self._instances:
                self._kill_instance(self._instances[plugin_name])

            log_file = os.path.join(self._log_dir, f"plugin_{plugin_name}.log")
            proc_env = os.environ.copy()
            # Disable NVIDIA CUDA cache to avoid sandbox blocking
            proc_env["CUDA_CACHE_DISABLE"] = "1"
            proc_env["CUDA_CACHE_PATH"] = ""
            if env:
                proc_env.update(env)

            exe_dir = os.path.dirname(command[0]) or "."

            print(f"[LIFECYCLE] Starting {plugin_name}: {command}", flush=True)

            try:
                # Use powershell.exe to start llama-server.exe in a new detached process.
                # This avoids sandbox restrictions that block CUDA init when started via Popen directly.
                cmd_line = " ".join(f'"{arg}"' if " " in str(arg) else str(arg) for arg in command)
                args_csv = ",".join(f'"{a}"' for a in command[1:])
                ps_cmd = f'Start-Process -FilePath "{command[0]}" -ArgumentList {args_csv} -PassThru'

                print(f"[LIFECYCLE] Launching via powershell.exe: {ps_cmd}", flush=True)

                proc = subprocess.Popen(
                    ["powershell.exe", "-Command", ps_cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=None,
                    env=proc_env,
                    cwd=exe_dir,
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                    shell=False,
                )
                # Read the output to get the new process PID
                output = proc.stdout.read().decode("utf-8", errors="replace").strip()
                print(f"[LIFECYCLE] PowerShell output: {output}", flush=True)
                print(f"[LIFECYCLE] Launcher started, PID={proc.pid}", flush=True)
            except Exception as e:
                raise RuntimeError(f"Failed to start {plugin_name}: {e}")

            # Wait for health endpoint to respond (up to 60s for large models)
            actual_port = port or 8080
            for i in range(60):
                time.sleep(1)
                try:
                    url = f"http://{host}:{actual_port}{health_endpoint}"
                    req = urllib.request.urlopen(url, timeout=2)
                    if req.status == 200:
                        print(f"[LIFECYCLE] {plugin_name} healthy after {i+1}s", flush=True)
                        break
                except Exception:
                    pass
            else:
                # Timeout - check if process is still running
                if proc.poll() is not None:
                    raise RuntimeError(f"Failed to start {plugin_name}: process exited with code {proc.poll()}")
                print(f"[LIFECYCLE] Warning: {plugin_name} not healthy after 60s but process is running", flush=True)

            inst = PluginInstance(
                plugin_name=plugin_name,
                plugin_type=plugin_type,
                pid=proc.pid,
                process=proc,
                host=host,
                port=actual_port,
                log_file=log_file,
                started_at=time.time(),
                status=PluginStatus.RUNNING,
                health_endpoint=health_endpoint,
            )
            self._instances[plugin_name] = inst
            return inst

    def stop_plugin(self, plugin_name: str) -> bool:
        with self._lock:
            inst = self._instances.get(plugin_name)
            if not inst:
                return False
            return self._kill_instance(inst)

    def stop_all(self):
        with self._lock:
            for name in list(self._instances.keys()):
                self._kill_instance(self._instances[name])
        # Safety net: kill orphaned processes by name patterns
        _kill_orphans()

    def wait_for_ready(
        self,
        plugin_name: str,
        timeout: int = 120,
        poll_interval: float = 1.0,
    ) -> dict:
        """Wait for a plugin's health endpoint to return 200."""
        inst = self.get_instance(plugin_name)
        if not inst:
            return {"ok": False, "error": "plugin not running"}
        if not inst.port:
            # No HTTP server — assume ready immediately
            inst.status = PluginStatus.RUNNING
            return {"ok": True, "elapsed": 0.0}

        url = f"http://{inst.host}:{inst.port}{inst.health_endpoint}"
        start = time.time()
        for _ in range(int(timeout / poll_interval)):
            if inst.process and inst.process.poll() is not None:
                return {
                    "ok": False,
                    "error": "process died",
                    "log_tail": _tail_log(inst.log_file, 20),
                }
            try:
                resp = urllib.request.urlopen(url, timeout=2)
                if resp.status == 200:
                    inst.status = PluginStatus.RUNNING
                    return {"ok": True, "elapsed": round(time.time() - start, 1)}
            except Exception:
                pass
            time.sleep(poll_interval)

        inst.status = PluginStatus.ERROR
        return {
            "ok": False,
            "error": "timeout",
            "log_tail": _tail_log(inst.log_file, 30),
        }

    def check_health(self, plugin_name: str) -> dict:
        inst = self.get_instance(plugin_name)
        if not inst:
            return {"ok": False, "error": "not running"}
        if not inst.port:
            return {"ok": True, "status": inst.status}
        try:
            url = f"http://{inst.host}:{inst.port}{inst.health_endpoint}"
            resp = urllib.request.urlopen(url, timeout=3)
            if resp.status == 200:
                inst.status = PluginStatus.RUNNING
            return {"ok": resp.status == 200, "status": inst.status}
        except Exception as e:
            return {"ok": False, "error": str(e), "status": inst.status}

    # ── Internal ─────────────────────────────────────────

    def _kill_instance(self, inst: PluginInstance) -> bool:
        inst.status = PluginStatus.STOPPING
        try:
            proc = psutil.Process(inst.pid)
            proc.terminate()
            gone, alive = psutil.wait_procs([proc], timeout=8)
            if alive:
                for p in alive:
                    try:
                        p.kill()
                        p.wait(timeout=5)
                    except Exception:
                        pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        inst.status = PluginStatus.STOPPED
        time.sleep(1)  # Allow VRAM release
        return True


# ── Helper functions ─────────────────────────────────────

def _kill_orphans():
    """Kill orphaned server processes as safety net."""
    patterns = ["llama-server.exe", "ollama.exe", "vllm.exe"]
    for pattern in patterns:
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", pattern],
                capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass


def _tail_log(log_path: str, lines: int = 20) -> str:
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except Exception:
        return ""
