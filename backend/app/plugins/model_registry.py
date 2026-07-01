"""
model_registry.py — Model Plugin Registry

Migrated from LiangLLM/model_manager.py.
Discovers GGUF models, classifies them into families, and manages
model plugin registration. Adapted for Life2Tea plugin architecture.
"""

import os
import re
import json
import threading
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import ConfigManager


# ── Default sampling parameters ──────────────────────────

DEFAULT_PARAMS = {
    "ngl": 99,
    "ctx": 32768,
    "batch": 1024,
    "ubatch": 512,
    "threads": 8,
    "cache_type_k": None,
    "cache_type_v": None,
    "flash_attn": False,
    "mmap": True,
    "mlock": False,
    "parallel": 1,
    "cont_batching": False,
    "temp": 0.7,
    "top_k": 40,
    "top_p": 0.9,
    "min_p": 0.0,
    "repeat_penalty": 1.1,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "mirostat": 0,
    "mirostat_tau": 5.0,
    "mirostat_eta": 0.1,
    "spec_type": "",
    "spec_draft_n_max": 2,
    "spec_draft_type_k": "f16",
    "spec_draft_type_v": "f16",
}

FAMILY_PARAMS = {
    "qwen3.6": {
        "ctx": 65536, "batch": 512, "ubatch": 512,
        "temp": 0.7, "top_k": 20, "top_p": 0.8, "min_p": 0.0,
        "presence_penalty": 1.5, "repeat_penalty": 1.05,
        "cache_type_k": None, "cache_type_v": None,
        "spec_type": "draft-mtp", "spec_draft_n_max": 2,
        "spec_draft_type_k": "f16", "spec_draft_type_v": "f16",
        "flash_attn": True, "reasoning": False,
    },
    "qwen3coder": {
        "ctx": 65536, "batch": 512, "ubatch": 512,
        "temp": 0.2, "top_k": 40, "top_p": 0.9,
    },
    "lfm2": {
        "ctx": 32768,
        "temp": 0.2, "top_k": 80, "repeat_penalty": 1.05,
    },
    "lfm2.5": {
        "ctx": 32768,
        "temp": 0.2, "top_k": 80, "repeat_penalty": 1.05,
    },
    "gemma4": {
        "ctx": 32768,
        "temp": 0.7, "top_k": 40,
    },
}

# Default port assignments for multi-model mode (single-model mode uses one port)
FAMILY_PORTS = {
    "lfm2.5": 8080, "lfm2": 8082, "gemma4": 8081,
    "qwen3.6": 8083, "qwen3coder": 8084, "qwen": 8085,
    "granite": 8086, "ministral": 8087, "glm": 8088,
}


@dataclass
class ModelInfo:
    family: str
    name: str
    display: str
    path: str
    size_gb: float
    quantization: str
    params_b: float
    default_port: int
    plugin_name: str = ""  # Associated plugin name
    default_params: dict = field(default_factory=dict)


def detect_quantization(filename: str) -> str:
    match = re.search(r'[Qq][0-9]_[A-Za-z0-9_]+', filename)
    return match.group(0).upper() if match else "unknown"


def is_model_disabled(model_family: str, config_mgr) -> bool:
    """Check if a model is disabled in configuration."""
    try:
        if config_mgr:
            # Try to get model config using family name
            config = config_mgr.get_model_config(model_family)
            if config and config.get("params", {}).get("disabled", False):
                return True
            # Also check plugin config
            plugin_config = config_mgr.get_plugin_config(model_family)
            if plugin_config and plugin_config.get("params", {}).get("disabled", False):
                return True
    except Exception:
        pass
    return False


def detect_params_from_filename(filename: str) -> float:
    name = filename.lower()
    patterns = [
        (r'(\d+\.?\d*)b', lambda m: float(m.group(1))),
        ("35b", 35.0), ("30b", 30.0), ("24b", 24.0),
        ("12b", 12.0), ("8b", 8.0), ("7b", 7.0),
        ("3b", 3.0), ("1b", 1.5),
    ]
    for pattern in patterns:
        if isinstance(pattern, tuple):
            if pattern[0] in name:
                return pattern[1] if not callable(pattern[1]) else pattern[1](re.search(pattern[0], name))
    return 0.0


def classify_family(name: str) -> Tuple[str, str]:
    n = name.lower()
    family_map = {
        "lfm2.5": ("lfm2.5", "LFM2.5"),
        "lfm2_5": ("lfm2.5", "LFM2.5"),
        "lfm2-24b": ("lfm2", "LFM2:24B"),
        "lfm2": ("lfm2", "LFM2"),
        "qwen3.6": ("qwen3.6", "Qwen3.6"),
        "qwen3_6": ("qwen3.6", "Qwen3.6"),
        "qwen3-coder": ("qwen3coder", "Qwen3-Coder"),
        "qwen3_coder": ("qwen3coder", "Qwen3-Coder"),
        "gemma4": ("gemma4", "Gemma4"),
        "gemma-4": ("gemma4", "Gemma4"),
        "granite": ("granite", "Granite"),
        "ministral": ("ministral", "Ministral"),
    }
    for key, (family, display) in family_map.items():
        if key in n:
            return family, display
    return n.replace("-", "_").replace(".", "_"), name


class ModelRegistry:
    """Discovers, classifies, and registers model plugins."""

    def __init__(self, models_dir: str, config_mgr=None):
        self._models_dir = models_dir
        self._registry: Dict[str, ModelInfo] = {}
        self._lock = threading.Lock()
        self.config_mgr = config_mgr
        self.scan()

    def scan(self) -> List[dict]:
        return self.list_models()

    def list_models(self) -> List[dict]:
        with self._lock:
            return [self._to_dict(m) for m in self._registry.values()]

    def get_model(self, family: str) -> Optional[ModelInfo]:
        with self._lock:
            return self._registry.get(family)

    def resolve_family(self, query: str) -> Optional[str]:
        q = query.lower().strip()
        with self._lock:
            if q in self._registry:
                return q
            for family in self._registry:
                if q in family or family in q:
                    return family
            for family, info in self._registry.items():
                if q in info.name.lower() or info.name.lower() in q:
                    return family
            return None

    def get_default_params(self, family: str) -> dict:
        info = self.get_model(family)
        params = dict(DEFAULT_PARAMS)
        if not info:
            return params
        for fam_key, overrides in FAMILY_PARAMS.items():
            if info.family.startswith(fam_key):
                params.update(overrides)
        # Merge user-configured model params (highest priority)
        user_config = self.config_mgr.get_model_config(info.name) if self.config_mgr else None
        if user_config and isinstance(user_config, dict):
            user_params = user_config.get("params", {})
            params.update(user_params)
        size = info.size_gb
        # Be conservative with context size for large models on 16GB GPU
        if size > 18:
            params["ctx"] = min(params.get("ctx", 32768), 16384)
        elif size > 12:
            # 13-18GB models on 16GB GPU: limit to 20K to leave room for KV cache
            params["ctx"] = min(params.get("ctx", 32768), 20480)
        elif size > 8:
            params["ctx"] = min(params.get("ctx", 32768), 32768)
        elif size < 4:
            params["ctx"] = max(params.get("ctx", 32768), 65536)
        return params

    def build_server_args(self, family: str, params: dict, server_exe: str, port: int = None) -> list:
        """Build command-line arguments for llama-server.exe."""
        info = self.get_model(family)
        if not info:
            raise ValueError(f"Unknown model family: {family}")

        # Convert paths to Windows format (backslashes) for llama-server.exe
        def to_linux_path(p: str) -> str:
            if not p:
                return p
            return p
