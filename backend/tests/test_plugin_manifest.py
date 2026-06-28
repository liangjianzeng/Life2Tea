"""
test_plugin_manifest.py — Unit tests for plugin manifest parsing.

Covers:
  - Valid model/expert/backend manifest parsing
  - ${VAR} expansion in model_path
  - Relative model_path resolution against manifest base_dir
  - Missing required keys → ValueError
  - Unknown type → ValueError
  - _BrokenManifest raises AttributeError on typed field access
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestModelManifestParsing:
    """Happy-path model manifest parsing."""

    def _make_raw(self, extra=None):
        raw = {
            "name": "lfm2",
            "version": "1.0.0",
            "type": "model",
            "display": "LFM2",
            "entry": {"runtime": "llama-server", "transport": "http"},
        }
        if extra:
            raw.update(extra)
        return raw

    def test_parse_minimal_model(self):
        from app.plugins.manifest import PluginManifest
        mf = PluginManifest.from_dict(self._make_raw())
        assert mf.name == "lfm2"
        assert mf.version == "1.0.0"
        assert mf.type == "model"
        assert mf.entry.runtime == "llama-server"
        assert mf.entry.transport == "http"

    def test_parse_full_model(self):
        from app.plugins.manifest import PluginManifest
        raw = self._make_raw({
            "model_family": "lfm2",
            "backend": "llama-cpp",
            "model_path": "${MODELS_DIR}/model.gguf",
            "port": 8082,
            "capabilities": ["chat"],
            "supports": {"streaming": True, "function_calling": True},
            "default_sampling_params": {
                "ctx": 32768, "temp": 0.2, "top_k": 80,
            },
        })
        mf = PluginManifest.from_dict(raw, env={"MODELS_DIR": "D:/models"})
        assert mf.model is not None
        assert mf.model.model_family == "lfm2"
        assert mf.model.backend == "llama-cpp"
        assert mf.model.model_path == "D:/models/model.gguf"
        assert mf.model.port == 8082
        assert mf.model.supports["streaming"] is True
        assert mf.model.default_sampling_params["ctx"] == 32768

    def test_relative_model_path_resolved(self):
        from app.plugins.manifest import PluginManifest
        raw = self._make_raw({
            "model_path": "models/model.gguf",
        })
        mf = PluginManifest.from_dict(
            raw,
            base_dir="/some/path/plugin",
            env={},
        )
        assert Path(mf.model.model_path).is_absolute()
        # Check the resolved path ends with the expected suffix (handles Windows drive letters)
        assert mf.model.model_path.endswith(
            os.sep + "some" + os.sep + "path" + os.sep + "plugin" + os.sep + "models" + os.sep + "model.gguf"
        )


class TestExpertManifestParsing:
    def test_parse_expert(self):
        from app.plugins.manifest import PluginManifest
        raw = {
            "name": "calculator",
            "version": "1.0.0",
            "type": "expert",
            "display": "Calculator",
            "entry": "module",
            "module": "app.plugins.experts.calculator",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "dangerous": False,
        }
        mf = PluginManifest.from_dict(raw)
        assert mf.type == "expert"
        assert mf.expert is not None
        assert mf.expert.input_schema == {"type": "object"}
        assert mf.expert.dangerous is False

    def test_parse_backend_type(self):
        from app.plugins.manifest import PluginManifest
        raw = {
            "name": "llama-cpp",
            "version": "1.0.0",
            "type": "backend",
            "entry": "llama-server",
        }
        mf = PluginManifest.from_dict(raw)
        assert mf.type == "backend"
        assert mf.model is None
        assert mf.expert is None


class TestValidationError:
    def test_missing_required_keys(self):
        from app.plugins.manifest import PluginManifest
        with pytest.raises(ValueError, match="missing required keys"):
            PluginManifest.from_dict({"name": "x"})

    def test_unknown_type(self):
        from app.plugins.manifest import PluginManifest
        raw = {"name": "x", "version": "1.0.0", "type": "unknown", "entry": "x"}
        with pytest.raises(ValueError, match="unknown plugin type"):
            PluginManifest.from_dict(raw)

    def test_non_dict_input(self):
        from app.plugins.manifest import PluginManifest
        with pytest.raises(ValueError, match="must be a JSON object"):
            PluginManifest.from_dict([1, 2])

    def test_bad_entry(self):
        from app.plugins.manifest import PluginManifest
        raw = {"name": "x", "version": "1.0.0", "type": "model", "entry": 42}
        with pytest.raises(ValueError, match="invalid entry"):
            PluginManifest.from_dict(raw)


class TestBrokenManifest:
    def test_raises_attribute_error(self):
        from app.plugins.registry import _BrokenManifest
        # _BrokenManifest is created with the manifest file path; name = parent dir (plugin name)
        bm = _BrokenManifest(Path("plugins/models/broken/manifest.json"))
        assert bm.name == "broken"
        assert bm.type == "unknown"
        with pytest.raises(AttributeError, match="failed to load"):
            bm.model


class TestFromActualFile:
    def test_lfm2_plugin_loads(self):
        """Load the real lfm2 manifest.json that lives in the repo."""
        from app.plugins.manifest import PluginManifest
        repo = Path(__file__).resolve().parents[2]  # project root
        path = repo / "plugins" / "models" / "lfm2" / "manifest.json"
        assert path.is_file(), f"lfm2 manifest not found at {path}"
        mf = PluginManifest.from_file(path)
        assert mf.name == "lfm2"
        assert mf.model is not None
        assert mf.model.model_family == "lfm2"
        assert mf.model.port == 8082
        assert mf.model.default_sampling_params["ctx"] == 32768
        assert mf.model.default_sampling_params["temp"] == 0.2


class TestModelInfoAdapter:
    def test_from_manifest(self):
        from app.plugins.manifest import PluginManifest
        from app.plugins.registry import ModelInfoAdapter
        raw = {
            "name": "gemma",
            "version": "1.0.0",
            "type": "model",
            "entry": "llama-server",
            "model_family": "gemma",
            "port": 9000,
            "default_sampling_params": {"ctx": 8192, "quantization": "Q4_K_M"},
        }
        mf = PluginManifest.from_dict(raw)
        adapter = ModelInfoAdapter.from_manifest(mf)
        assert adapter.family == "gemma"
        assert adapter.name == "gemma"
        assert adapter.default_port == 9000
        assert adapter.default_params["ctx"] == 8192
        assert adapter.to_dict()["source"] == "plugin"
