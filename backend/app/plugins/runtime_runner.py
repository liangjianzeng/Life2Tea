"""
runtime_runner.py — Unified plugin runtime runner.

Routes to SubprocessRunner (model) or InprocLoader (expert) based on
plugin type. This is the preferred high-level API for loading plugins.

Usage:

    runner = PluginRunner(log_dir="logs", env={"MODELS_DIR": "D:/models"})
    instance = runner.run_plugin("lfm2", manifest, plugin_type="model")
    instance.pid, instance.port  # Ready to use
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

from .base import IExpertPlugin, IModelPlugin, PluginState
from .manifest import PluginManifest
from .subprocess_runner import SubprocessRunner
from .inproc_loader import InprocLoader


class PluginRunner:
    """Runs plugins with appropriate runtime based on type."""

    def __init__(
        self,
        *,
        log_dir: str = ".",
        env: Optional[Dict[str, str]] = None,
    ):
        self.log_dir = Path(log_dir)
        self.env = dict(os.environ)
        if env:
            self.env.update(env)
        self._subprocess_runner: Optional[SubprocessRunner] = None
        self._inproc_loader: Optional[InprocLoader] = None

    def _get_subprocess_runner(self) -> SubprocessRunner:
        if self._subprocess_runner is None:
            self._subprocess_runner = SubprocessRunner(
                health_endpoint="/health",
                health_timeout=2,
                max_wait_seconds=180,
                poll_interval=1.0,
                log_dir=str(self.log_dir),
                env=self.env,
            )
        return self._subprocess_runner

    def _get_inproc_loader(self) -> InprocLoader:
        if self._inproc_loader is None:
            self._inproc_loader = InprocLoader(env=self.env)
        return self._inproc_loader

    def run_model_plugin(self, manifest: PluginManifest) -> Dict[str, any]:
        """
        Start a model plugin (subprocess, HTTP-based).

        Returns:
            dict with keys: pid, host, port, process, log_file, status
        """
        m = manifest.model
        if not m:
            raise ValueError("manifest.model is required for model plugins")

        runner = self._get_subprocess_runner()

        # Build command from entry spec
        command = self._build_model_command(manifest)
        if not command:
            raise ValueError("Could not build command for model plugin")

        # Determine port (manifest.port > entry.port > default 8082)
        port = manifest.model.port or 8082

        instance = runner.start(
            command=command,
            host=manifest.entry.transport == "http" and "127.0.0.1" or "localhost",
            port=port,
            name=manifest.name,
        )

        return {
            "pid": instance.pid,
            "host": instance.host,
            "port": instance.port,
            "process": instance.process,
            "log_file": instance.log_file,
            "status": "running",
        }

    def run_expert_plugin(
        self,
        manifest: PluginManifest,
    ) -> Dict[str, any]:
        """
        Load an expert plugin (in-process, Python module).

        Returns:
            dict with keys: name, plugin, module_path, status
        """
        if not manifest.expert:
            raise ValueError("manifest.expert is required for expert plugins")

        loader = self._get_inproc_loader()
        module_path = manifest.entry.module or manifest.name

        try:
            instance = loader.load(
                module_path=module_path,
                manifest_data=manifest.expert.input_schema,
            )
        except Exception as e:
            # Fallback: try to import from plugins.experts namespace
            try:
                fallback_path = f"app.plugins.experts.{module_path}"
                instance = loader.load(
                    module_path=fallback_path,
                    manifest_data=manifest.expert.input_schema,
                )
            except Exception as e2:
                raise RuntimeError(
                    f"Failed to load expert plugin {manifest.name}: {e2}"
                ) from e2

        return {
            "name": instance.name,
            "plugin": instance.plugin,
            "module_path": instance.module_path,
            "status": "running",
        }

    def _build_model_command(
        self, manifest: PluginManifest
    ) -> List[str]:
        """Build the command line for a model plugin."""
        m = manifest.model
        if not m:
            return []

        entry = manifest.entry

        # If entry.command is explicitly set, use it
        if entry.command:
            return list(entry.command)

        # Otherwise, build from entry.runtime + manifest fields
        if entry.runtime == "llama-server":
            cmd = [
                self._resolve_llama_server_exe(),
                "--port", str(m.port or 8082),
                "--model", m.model_path,
            ]

            # Add sampling params
            sp = m.default_sampling_params
            if "ctx" in sp:
                cmd.extend(["-c", str(sp["ctx"])])
            if "ngl" in sp:
                cmd.extend(["-ngl", str(sp["ngl"])])
            if "temp" in sp:
                cmd.extend(["--temp", str(sp["temp"])])
            if "top_k" in sp:
                cmd.extend(["--top-k", str(sp["top_k"])])
            if "repeat_penalty" in sp:
                cmd.extend(["--repeat-penalty", str(sp["repeat_penalty"])])
            if "batch" in sp:
                cmd.extend(["-b", str(sp["batch"])])
            if "ubatch" in sp:
                cmd.extend(["-ub", str(sp["ubatch"])])
            if "threads" in sp:
                cmd.extend(["--threads", str(sp["threads"])])

            return cmd

        raise NotImplementedError(
            f"runtime={entry.runtime!r} not supported for model plugins"
        )

    def _resolve_llama_server_exe(self) -> str:
        """Find the llama-server.exe path."""
        # Try common locations
        candidates = [
            "D:/MyLLM/llama.cpp/llama-server.exe",
            "D:/tools/llama.cpp/llama-server.exe",
            "C:/Program Files/llama.cpp/llama-server.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        # If none found, return first candidate (will fail at runtime)
        return candidates[0]

    def stop_plugin(self, plugin_type: str, instance: dict) -> bool:
        """Stop a running plugin instance."""
        if plugin_type == "model":
            proc = instance.get("process")
            if proc:
                import psutil
                try:
                    p = psutil.Process(instance["pid"])
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    pass
            return True
        elif plugin_type == "expert":
            plugin = instance.get("plugin")
            if plugin:
                try:
                    plugin.unload()
                except Exception:
                    pass
            return True
        return False


__all__ = ["PluginRunner"]
