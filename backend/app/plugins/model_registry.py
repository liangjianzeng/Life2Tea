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
    "cache_type_k": "q8_0",
    "cache_type_v": "q8_0",
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
        "cache_type_k": "q8_0", "cache_type_v": "q8_0",
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

    def __init__(self, models_dir: str):
        self._models_dir = models_dir
        self._registry: Dict[str, ModelInfo] = {}
        self._lock = threading.Lock()
        self._scan()

    def scan(self) -> List[dict]:
        self._scan()
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
        size = info.size_gb
        if size > 18:
            params["ctx"] = min(params.get("ctx", 32768), 16384)
        elif size > 12:
            params["ctx"] = min(params.get("ctx", 32768), 24576)
        elif size < 4:
            params["ctx"] = max(params.get("ctx", 32768), 65536)
        return params

    def build_server_args(self, family: str, params: dict, server_exe: str) -> list:
        """Build command-line arguments for llama-server.exe."""
        info = self.get_model(family)
        if not info:
            raise ValueError(f"Unknown model family: {family}")

        args = [server_exe]
        args += ["--model", info.path]
        args += ["-ngl", str(params.get("ngl", 99))]
        args += ["-c", str(params.get("ctx", 32768))]
        args += ["--parallel", str(params.get("parallel", 1))]
        args += ["--threads", str(params.get("threads", 8))]
        args += ["-b", str(params.get("batch", 1024))]
        args += ["-ub", str(params.get("ubatch", 512))]
        args += ["--cache-type-k", params.get("cache_type_k", "q8_0")]
        args += ["--cache-type-v", params.get("cache_type_v", "q8_0")]

        if params.get("mmap", True):
            args += ["--mmap"]
        if params.get("mlock", False):
            args += ["--mlock"]
        if params.get("flash_attn", False):
            args += ["--flash-attn"]
        if params.get("cont_batching", False):
            args += ["--cont-batching"]

        args += ["--no-warmup"]
        args += ["--temp", str(params.get("temp", 0.7))]
        args += ["--top-k", str(params.get("top_k", 40))]
        args += ["--top-p", str(params.get("top_p", 0.9))]
        args += ["--min-p", str(params.get("min_p", 0.0))]
        args += ["--repeat-penalty", str(params.get("repeat_penalty", 1.1))]

        if params.get("presence_penalty", 0.0) != 0.0:
            args += ["--presence-penalty", str(params["presence_penalty"])]
        if params.get("frequency_penalty", 0.0) != 0.0:
            args += ["--frequency-penalty", str(params["frequency_penalty"])]

        mirostat = params.get("mirostat", 0)
        if mirostat > 0:
            args += ["--mirostat", str(mirostat)]
            args += ["--mirostat-tau", str(params.get("mirostat_tau", 5.0))]
            args += ["--mirostat-eta", str(params.get("mirostat_eta", 0.1))]

        spec_type = params.get("spec_type", "")
        if spec_type:
            args += ["--spec-type", spec_type]
            args += ["--spec-draft-n-max", str(params.get("spec_draft_n_max", 2))]
            args += ["--spec-draft-type-k", params.get("spec_draft_type_k", "f16")]
            args += ["--spec-draft-type-v", params.get("spec_draft_type_v", "f16")]

        args += ["--alias", family]

        reasoning = params.get("reasoning")
        if reasoning is not None:
            args += ["--reasoning", "on" if reasoning else "off"]

        return args

    # ── Internal ──────────────────────────────────────────

    def _scan(self):
        registry = {}
        if not os.path.isdir(self._models_dir):
            self._registry = registry
            return

        for root, dirs, files in os.walk(self._models_dir):
            for f in sorted(files):
                if not f.endswith(".gguf") or "mmproj" in f:
                    continue
                path = os.path.join(root, f)
                name = f.replace(".gguf", "")
                size_gb = os.path.getsize(path) / (1024 ** 3)
                quant = detect_quantization(f)
                params_b = detect_params_from_filename(f)
                family, display = classify_family(name)
                default_port = FAMILY_PORTS.get(family, 9090)

                info = ModelInfo(
                    family=family, name=name, display=display,
                    path=path, size_gb=round(size_gb, 1),
                    quantization=quant, params_b=params_b,
                    default_port=default_port,
                )
                registry[family] = info

        self._registry = registry

    def _to_dict(self, info: ModelInfo) -> dict:
        return {
            "family": info.family,
            "name": info.name,
            "display": info.display,
            "path": info.path,
            "size_gb": info.size_gb,
            "quantization": info.quantization,
            "params_b": info.params_b,
            "default_port": info.default_port,
            "plugin_name": info.plugin_name,
        }
