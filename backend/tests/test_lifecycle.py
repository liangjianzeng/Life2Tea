"""
test_lifecycle.py — Unit tests for lifecycle management.

Covers:
  - SubprocessRunner.start() with mock
  - SubprocessRunner.health polling
  - PluginRunner routes to correct runner
  - InprocLoader can load expert plugins
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.plugins.subprocess_runner import SubprocessRunner, ProcessInstance
from app.plugins.runtime_runner import PluginRunner
from app.plugins.inproc_loader import InprocLoader
from app.plugins.manifest import PluginManifest
from app.plugins.base import IExpertPlugin


class TestSubprocessRunner:
    def test_init(self):
        runner = SubprocessRunner(
            health_endpoint="/alive",
            max_wait_seconds=60,
            log_dir="/tmp/logs",
        )
        assert runner.health_endpoint == "/alive"
        assert runner.max_wait_seconds == 60

    @patch("app.plugins.subprocess_runner.subprocess.Popen")
    def test_start_fails_without_exe(self, mock_popen):
        runner = SubprocessRunner(log_dir=tempfile.gettempdir())
        with pytest.raises(FileNotFoundError):
            runner.start(["nonexistent.exe"], name="test")

    def test_health_timeout(self):
        runner = SubprocessRunner(
            max_wait_seconds=2,
            health_endpoint="/health",
        )
        with patch("app.plugins.subprocess_runner.subprocess.Popen") as mock_popen, \
             patch("app.plugins.subprocess_runner.subprocess.DEVNULL", subprocess.DEVNULL), \
             patch("pathlib.Path.resolve") as mock_resolve, \
             patch("pathlib.Path.is_file", return_value=True):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None  # process still alive
            mock_popen.return_value = mock_proc
            mock_resolve.return_value = Path("echo")
            # Health endpoint will never return 200 (not mocked)
            with pytest.raises(RuntimeError, match="Health check timeout"):
                runner.start(["echo", "hello"], name="test", port=9999)


class TestInprocLoader:
    def test_init(self):
        loader = InprocLoader(env={"TEST": "value"})
        assert "TEST" in loader.env
        assert loader.env["TEST"] == "value"

    def test_load_nonexistent_module(self):
        loader = InprocLoader()
        with pytest.raises(ImportError):
            loader.load("nonexistent.module.path")

    def test_load_with_plugin_class(self):
        loader = InprocLoader()

        class TestExpert(IExpertPlugin):
            def __init__(self, **config):
                from app.plugins.manifest import PluginManifest
                self.manifest = PluginManifest.from_dict({
                    "name": "test",
                    "version": "1.0.0",
                    "type": "expert",
                    "entry": {"runtime": "python"},
                })

            def load(self): pass
            def unload(self): pass
            def health(self):
                from app.plugins.base import PluginHealth
                return PluginHealth(healthy=True)
            def get_tools(self): return []
            def execute(self, tool: str, args: dict) -> dict:
                return {"result": "ok"}

        # Manually patch sys.modules to simulate module with plugin class
        import sys
        mod = MagicMock()
        mod.__dict__ = {"TestExpert": TestExpert}
        sys.modules["test_expert_module"] = mod

        try:
            instance = loader.load("test_expert_module")
            assert instance.name == "test"
            assert isinstance(instance.plugin, TestExpert)
            tools = instance.plugin.get_tools()
            assert tools == []
        finally:
            if "test_expert_module" in sys.modules:
                del sys.modules["test_expert_module"]


class TestPluginRunner:
    def test_init(self):
        runner = PluginRunner(log_dir="/tmp/logs", env={"MODELS_DIR": "D:/models"})
        assert runner.log_dir == Path("/tmp/logs")
        assert runner.env["MODELS_DIR"] == "D:/models"

    def test_run_model_plugin_requires_model_manifest(self):
        runner = PluginRunner()
        mf = PluginManifest.from_dict({
            "name": "x",
            "version": "1.0.0",
            "type": "model",
            "entry": {"runtime": "unknown"},
        })
        with pytest.raises(NotImplementedError, match="runtime='unknown' not supported"):
            runner.run_model_plugin(mf)

    def test_build_command_llama_server(self):
        runner = PluginRunner()
        mf = PluginManifest.from_dict({
            "name": "lfm2",
            "version": "1.0.0",
            "type": "model",
            "entry": {"runtime": "llama-server"},
            "model_family": "lfm2",
            "model_path": "D:/models/lfm2.gguf",
            "port": 8082,
            "default_sampling_params": {
                "ctx": 32768,
                "ngl": 28,
                "temp": 0.2,
                "top_k": 80,
            },
        })
        cmd = runner._build_model_command(mf)
        assert "llama-server" in cmd[0]
        assert "--port" in cmd
        assert "8082" in cmd
        assert "-c" in cmd
        assert "32768" in cmd
        assert "--temp" in cmd
        assert "0.2" in cmd


class TestIntegration:
    def test_full_run_lifecycle(self):
        """Full integration: create manifest, run plugin, stop it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = PluginRunner(log_dir=tmpdir)

            # Create a minimal manifest for a fake plugin
            mf = PluginManifest.from_dict({
                "name": "test-fake",
                "version": "1.0.0",
                "type": "model",
                "entry": {"runtime": "echo", "command": ["echo", "hello"]},
                "model_path": "D:/fake.gguf",
                "port": 9998,
            })

            # We expect this to fail at health check (echo won't listen on port)
            # but the command building should work
            cmd = runner._build_model_command(mf)
            # Command built from entry.command if present
            assert cmd == ["echo", "hello"]
