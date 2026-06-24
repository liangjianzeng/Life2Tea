"""
metrics.py — Plugin Performance Metrics Collection

Migrated from LiangLLM/metrics_collector.py.
Collects and aggregates inference performance metrics per plugin.
Adapted for Life2Tea: tracks by plugin_name instead of model_family.
"""

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class InferenceRecord:
    plugin_name: str       # Plugin name (not just model family)
    tokens_generated: int
    prompt_tokens: int
    elapsed_seconds: float
    tokens_per_second: float
    timestamp: float = field(default_factory=time.time)
    temperature: float = 0.0
    max_tokens: int = 0
    backend: str = ""      # "llama-cpp", "ollama", etc.


class MetricsCollector:
    """Collects and aggregates inference performance statistics per plugin."""

    def __init__(self, max_history: int = 1000):
        self._history: deque = deque(maxlen=max_history)
        self._session_stats: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def record_inference(self, record: InferenceRecord):
        with self._lock:
            self._history.append(record)
            fam = record.plugin_name
            if fam not in self._session_stats:
                self._session_stats[fam] = {
                    "total_inferences": 0,
                    "total_tokens": 0,
                    "total_prompt_tokens": 0,
                    "total_time_seconds": 0.0,
                    "max_tps": 0.0,
                    "min_tps": float('inf'),
                    "backends": set(),
                }
            s = self._session_stats[fam]
            s["total_inferences"] += 1
            s["total_tokens"] += record.tokens_generated
            s["total_prompt_tokens"] += record.prompt_tokens
            s["total_time_seconds"] += record.elapsed_seconds
            s["max_tps"] = max(s["max_tps"], record.tokens_per_second)
            s["min_tps"] = min(s["min_tps"], record.tokens_per_second)
            if record.backend:
                s["backends"].add(record.backend)

    # ── Query Methods ─────────────────────────────────────

    def get_plugin_stats(self, plugin_name: str) -> dict:
        with self._lock:
            base = self._session_stats.get(plugin_name, {})
            if not base:
                return {
                    "plugin_name": plugin_name,
                    "total_inferences": 0,
                    "total_tokens": 0,
                    "avg_tps": 0,
                    "max_tps": 0,
                    "min_tps": 0,
                }
            avg_tps = (base["total_tokens"] / base["total_time_seconds"]
                       if base["total_time_seconds"] > 0 else 0)
            min_tps = base["min_tps"] if base["min_tps"] != float('inf') else 0
            return {
                "plugin_name": plugin_name,
                "total_inferences": base["total_inferences"],
                "total_tokens": base["total_tokens"],
                "total_prompt_tokens": base["total_prompt_tokens"],
                "total_time_seconds": round(base["total_time_seconds"], 2),
                "avg_tps": round(avg_tps, 2),
                "max_tps": round(base["max_tps"], 2),
                "min_tps": round(min_tps, 2),
                "backends": list(base.get("backends", set())),
            }

    def get_all_stats(self) -> List[dict]:
        with self._lock:
            return [self.get_plugin_stats(name) for name in self._session_stats]

    def get_recent_inferences(self, limit: int = 20) -> List[dict]:
        with self._lock:
            records = list(self._history)[-limit:]
            return [{
                "plugin_name": r.plugin_name,
                "tokens_generated": r.tokens_generated,
                "prompt_tokens": r.prompt_tokens,
                "elapsed_seconds": round(r.elapsed_seconds, 2),
                "tokens_per_second": round(r.tokens_per_second, 2),
                "temperature": r.temperature,
                "backend": r.backend,
                "timestamp": r.timestamp,
                "time_str": datetime.fromtimestamp(r.timestamp).strftime("%H:%M:%S"),
            } for r in records]

    def get_summary(self) -> dict:
        with self._lock:
            total_inf = sum(s["total_inferences"] for s in self._session_stats.values())
            total_tok = sum(s["total_tokens"] for s in self._session_stats.values())
            total_time = sum(s["total_time_seconds"] for s in self._session_stats.values())
            return {
                "total_inferences": total_inf,
                "total_tokens": total_tok,
                "total_time_seconds": round(total_time, 2),
                "avg_tps_all": round(total_tok / total_time, 2) if total_time > 0 else 0,
                "plugin_count": len(self._session_stats),
                "active_plugins": list(self._session_stats.keys()),
            }

    def reset(self):
        with self._lock:
            self._history.clear()
            self._session_stats.clear()
