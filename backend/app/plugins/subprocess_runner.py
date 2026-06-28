"""
subprocess_runner.py — Subprocess plugin runner (model plugins).

Starts a model plugin (e.g. llama-server, ollama) as a sub-process and
monitors its health endpoint until it's ready.

Design:
  - SubprocessRunner.start() launches the process + health wait
  - Returns a ProcessInstance (PID, host, port, log_file)
  - No PowerShell wrapper — direct Popen with proper flags

Why not PowerShell?
  - PowerShell Start-Process PID detection is unreliable on Windows
  - Direct Popen + DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP works fine
"""

import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class ProcessInstance:
    """Result of a successful process start."""
    pid: int
    host: str
    port: int
    process: Optional[subprocess.Popen] = None
    log_file: str = ""
    started_at: float = field(default_factory=time.time)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "log_file": self.log_file,
        }


class SubprocessRunner:
    """Starts and monitors subprocess-based plugins (model runners)."""

    def __init__(
        self,
        *,
        health_endpoint: str = "/health",
        health_timeout: int = 2,
        max_wait_seconds: int = 180,
        poll_interval: float = 1.0,
        log_dir: Optional[str] = None,
        env: Optional[dict] = None,
    ):
        """
        Args:
            health_endpoint: HTTP path to probe (e.g. "/health")
            health_timeout: urllib timeout in seconds
            max_wait_seconds: How long to wait for health before giving up
            poll_interval: Seconds between health probes
            log_dir: Where to write process stdout/stderr logs
            env: Extra environment variables to merge over os.environ
        """
        self.health_endpoint = health_endpoint
        self.health_timeout = health_timeout
        self.max_wait_seconds = max_wait_seconds
        self.poll_interval = poll_interval
        self.log_dir = Path(log_dir) if log_dir else Path(".")
        self.env = dict(os.environ)
        if env:
            self.env.update(env)

    def start(
        self,
        command: List[str],
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        name: str = "plugin",
    ) -> ProcessInstance:
        """
        Start a subprocess plugin and wait for health.

        Args:
            command: Full argv list (e.g. ["llama-server.exe", "--port", "8080"])
            host: Bind address
            port: If None, use the port from command args or 8080
            name: Human-readable name for logging

        Returns:
            ProcessInstance with PID, host, port, process handle

        Raises:
            RuntimeError: If process exits or health never responds
        """
        # Parse port from command if not explicitly given
        actual_port = port
        if actual_port is None:
            for i, arg in enumerate(command):
                if arg == "--port" and i + 1 < len(command):
                    try:
                        actual_port = int(command[i + 1])
                        break
                    except ValueError:
                        pass

        if actual_port is None:
            actual_port = 8080

        log_file = str(self.log_dir / f"plugin_{name}_{actual_port}.log")
        exe_path = Path(command[0]).resolve()

        # Ensure executable exists
        if not exe_path.is_file():
            raise FileNotFoundError(f"Executable not found: {exe_path}")

        # Build Popen kwargs
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW
            )

        proc_env = dict(self.env)
        # Disable CUDA cache to avoid sandbox issues
        proc_env["CUDA_CACHE_DISABLE"] = "1"
        proc_env["CUDA_CACHE_PATH"] = ""

        # Open log file before starting process
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8", errors="replace")

        try:
            # Start process with stdout/stderr redirected to log file
            proc = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=log_handle,
                stdin=subprocess.DEVNULL,
                env=proc_env,
                creationflags=creation_flags,
            )
            pid = proc.pid

            # Wait for health endpoint
            if not self._wait_for_health(host, actual_port, name):
                # Process may have crashed; check exit code
                exit_code = proc.poll()
                if exit_code is not None:
                    log_tail = self._tail_log(log_file, 30)
                    raise RuntimeError(
                        f"Process exited with code {exit_code}. "
                        f"Log:\n{log_tail}"
                    )
                raise RuntimeError(
                    f"Health check timeout after {self.max_wait_seconds}s. "
                    f"Process {pid} still running but {host}:{actual_port}{self.health_endpoint} not responding."
                )

            return ProcessInstance(
                pid=pid,
                host=host,
                port=actual_port,
                process=proc,
                log_file=log_file,
                started_at=time.time(),
            )

        except Exception:
            # Cleanup on failure
            log_handle.close()
            # Try to kill the process if it started
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
            except Exception:
                pass
            raise

    def _wait_for_health(self, host: str, port: int, name: str) -> bool:
        """Poll health endpoint until ready or timeout."""
        url = f"http://{host}:{port}{self.health_endpoint}"
        start = time.time()

        while time.time() - start < self.max_wait_seconds:
            try:
                req = urllib.request.urlopen(
                    url, timeout=self.health_timeout
                )
                if req.status == 200:
                    print(
                        f"[SubprocessRunner] {name} healthy after "
                        f"{time.time() - start:.1f}s at {url}",
                        flush=True,
                    )
                    return True
            except (urllib.error.URLError, urllib.error.HTTPError):
                pass  # Endpoint not ready yet
            except Exception as e:
                print(
                    f"[SubprocessRunner] Health probe error: {e}", flush=True
                )
                # Don't fail on probe errors; process may still be coming up

            time.sleep(self.poll_interval)

        return False

    def _tail_log(self, log_path: str, lines: int = 20) -> str:
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-lines:])
        except Exception:
            return ""


__all__ = ["SubprocessRunner", "ProcessInstance"]
