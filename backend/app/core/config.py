"""
config.py — Life2Tea Configuration Profiles Persistence

Migrated from LiangLLM/config_manager.py.
Manages global config, model-specific configs, and cross-model parameter profiles.
Adapted for plugin architecture: configs are now keyed by plugin name.
"""

import json
import os
import threading
from datetime import datetime
from typing import Optional, Dict, List


DEFAULT_GLOBAL = {
    "theme": "dark",
    "language": "zh-CN",
    "backend_preference": "auto",
    "llama_backend_dir": "",
    "llama_server_exe": "",
    "models_dir": "",
    "default_port_range": [8080, 8099],
    "default_host": "127.0.0.1",
    "startup_behavior": "idle",
    "auto_load_model": None,
    "last_loaded_model": None,
    "gpu_layers": 99,
    "ctx_size": 32768,
    "threads": 0,
    "batch_size": 1024,
    "mmap": True,
    "mlock": False,
    "flash_attn": False,
    "cont_batching": False,
    "parallel": 1,
    "log_level": "info",
    "log_retention_days": 30,
    "api_key": "",
    "api_provider": "llama-cpp",
    "api_base_url": "",
    "auto_update_check": True,
    "telemetry": False,
    "max_startup_wait_seconds": 120,
    # Life2Tea extensions
    "plugin_dirs": ["plugins/models", "plugins/experts"],
    "resource_budget": {
        "vram_mb": 0,
        "ram_mb": 0,
        "cpu_cores": 0,
        "strategy": "evict_lru",
    },
}


class ConfigManager:
    """Persistent configuration for Life2Tea."""

    def __init__(self, config_dir: str):
        self._config_dir = config_dir
        self._profiles_dir = os.path.join(config_dir, "profiles")
        self._global_config_path = os.path.join(config_dir, "life2tea.json")
        self._lock = threading.RLock()
        os.makedirs(self._profiles_dir, exist_ok=True)

    # ── Global Config ───────────────────────────────────────

    def get_global(self) -> dict:
        if not os.path.isfile(self._global_config_path):
            return dict(DEFAULT_GLOBAL)
        with self._lock:
            try:
                with open(self._global_config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                merged = dict(DEFAULT_GLOBAL)
                merged.update(saved)
                if merged != saved:
                    self.save_global(merged)
                return merged
            except Exception:
                return dict(DEFAULT_GLOBAL)

    def save_global(self, config: dict):
        with self._lock:
            config["_updated_at"] = datetime.now().isoformat()
            with open(self._global_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

    # ── Plugin-Specific Config ─────────────────────────────

    def get_plugin_config(self, plugin_name: str) -> Optional[dict]:
        path = self._plugin_config_path(plugin_name)
        if not os.path.isfile(path):
            return None
        with self._lock:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

    def save_plugin_config(self, plugin_name: str, params: dict):
        path = self._plugin_config_path(plugin_name)
        with self._lock:
            data = {
                "plugin": plugin_name,
                "params": params,
                "_updated_at": datetime.now().isoformat(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def delete_plugin_config(self, plugin_name: str) -> bool:
        path = self._plugin_config_path(plugin_name)
        if not os.path.isfile(path):
            return False
        with self._lock:
            os.remove(path)
            return True

    # ── Profiles (cross-plugin presets) ──────────────────

    def list_profiles(self) -> List[dict]:
        profiles = []
        if not os.path.isdir(self._profiles_dir):
            return profiles
        with self._lock:
            for fname in sorted(os.listdir(self._profiles_dir)):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(self._profiles_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    profiles.append({
                        "name": data.get("name", fname[:-5]),
                        "description": data.get("description", ""),
                        "params": data.get("params", {}),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                    })
                except Exception:
                    continue
        return profiles

    def get_profile(self, name: str) -> Optional[dict]:
        path = os.path.join(self._profiles_dir, f"{name}.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_profile(self, name: str, params: dict, description: str = ""):
        path = os.path.join(self._profiles_dir, f"{name}.json")
        now = datetime.now().isoformat()
        existing = self.get_profile(name)
        data = {
            "name": name,
            "description": description,
            "params": params,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def delete_profile(self, name: str) -> bool:
        path = os.path.join(self._profiles_dir, f"{name}.json")
        if not os.path.isfile(path):
            return False
        with self._lock:
            os.remove(path)
            return True

    # ── Internal ───────────────────────────────────────────

    def _plugin_config_path(self, plugin_name: str) -> str:
        safe = plugin_name.replace("/", "_").replace("\\", "_").replace("..", "_")
        return os.path.join(self._config_dir, f"plugin_{safe}.json")
