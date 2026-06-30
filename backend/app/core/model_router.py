"""
model_router.py — Unified Model Router for Life2Tea

Implements unified model routing with:
- Model name-based routing (explicit model selection)
- Idle load balancing (automatic model assignment)
- Integration with existing API key/stats infrastructure
"""

import os
import json
import threading
import time
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from ..core.config import ConfigManager


class LoadBalanceStrategy(Enum):
    IDLE = "idle"  # Route to least loaded model
    ROUND_ROBIN = "round_robin"
    PRIORITY = "priority"  # Use priority list


@dataclass
class ModelInstance:
    family: str
    port: int
    host: str = "127.0.0.1"
    status: str = "unknown"
    last_used: float = field(default_factory=time.time)
    request_count: int = 0


class ModelRouter:
    """
    Unified model router that manages multiple model instances and routes
    requests based on model name or idle load balancing.
    """

    def __init__(
        self,
        config_mgr: ConfigManager,
        stats_service = None,  # Optional, for load balancing
        default_port_range: Tuple[int, int] = (8080, 8099),
    ):
        self.config_mgr = config_mgr
        self.stats_service = stats_service
        self.default_port_range = default_port_range
        
        self._instances: Dict[str, ModelInstance] = {}
        self._lock = threading.Lock()
        
        # Load persistent state
        self._config_file = Path("config/model_router.json")
        self._load_state()
        
        # Common models to expose on unified endpoint
        self._common_models = ["qwen3.6", "glm", "lfm2"]
        
    def _load_state(self):
        """Load router state from config file."""
        if self._config_file.exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    for family, data in state.get("instances", {}).items():
                        self._instances[family] = ModelInstance(**data)
            except Exception as e:
                print(f"[ModelRouter] Failed to load state: {e}", flush=True)
    
    def _save_state(self):
        """Save router state to config file."""
        try:
            state = {
                "instances": {
                    family: {"family": i.family, "port": i.port, "host": i.host}
                    for family, i in self._instances.items()
                },
                "last_updated": time.time(),
            }
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ModelRouter] Failed to save state: {e}", flush=True)
    
    def register_instance(self, family: str, port: int, host: str = "127.0.0.1"):
        """Register a running model instance."""
        with self._lock:
            instance = ModelInstance(
                family=family,
                port=port,
                host=host,
                status="running",
            )
            self._instances[family] = instance
            self._save_state()
            print(f"[ModelRouter] Registered {family} on port {port}", flush=True)
    
    def unregister_instance(self, family: str):
        """Unregister a model instance."""
        with self._lock:
            if family in self._instances:
                del self._instances[family]
                self._save_state()
                print(f"[ModelRouter] Unregistered {family}", flush=True)
    
    def get_instance(self, family: str) -> Optional[ModelInstance]:
        """Get instance by family name."""
        with self._lock:
            return self._instances.get(family)
    
    def list_instances(self) -> List[ModelInstance]:
        """List all registered instances."""
        with self._lock:
            return list(self._instances.values())
    
    def find_instance_by_name(self, model_name: str) -> Optional[ModelInstance]:
        """
        Find instance by exact or partial model name match.
        Returns the first matching instance.
        """
        with self._lock:
            model_lower = model_name.lower().strip()
            for family, instance in self._instances.items():
                if model_lower == family.lower() or model_lower in family.lower():
                    return instance
            return None
    
    def get_idle_instance(self) -> Optional[ModelInstance]:
        """
        Get the least loaded instance using idle-based load balancing.
        Uses request count from stats service as load metric.
        """
        with self._lock:
            if not self._instances:
                return None
            
            # Get current request counts from stats if available
            request_counts = {}
            try:
                if self.stats_service:
                    request_counts = self.stats_service.get_api_key_stats()
            except Exception:
                pass
            
            # Find instance with lowest request count
            best_instance = None
            lowest_count = float("inf")
            
            for family, instance in self._instances.items():
                # Get request count for this model (using family as key)
                count = request_counts.get(family, {}).get("request_count", 0)
                if count < lowest_count:
                    lowest_count = count
                    best_instance = instance
            
            # Update last used time
            if best_instance:
                best_instance.last_used = time.time()
                best_instance.request_count = lowest_count
            
            return best_instance
    
    def route_request(
        self,
        model_name: Optional[str] = None,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.IDLE,
    ) -> Optional[ModelInstance]:
        """
        Route a request to an appropriate model instance.
        
        Args:
            model_name: Explicit model name (if None, use strategy)
            strategy: Load balancing strategy
            
        Returns:
            ModelInstance or None if no suitable instance found
        """
        # If explicit model name provided, find it
        if model_name:
            instance = self.find_instance_by_name(model_name)
            if instance:
                return instance
        
        # Use load balancing strategy
        if strategy == LoadBalanceStrategy.IDLE:
            return self.get_idle_instance()
        elif strategy == LoadBalanceStrategy.ROUND_ROBIN:
            return self._round_robin()
        
        return None
    
    def _round_robin(self) -> Optional[ModelInstance]:
        """Round-robin selection among instances."""
        with self._lock:
            if not self._instances:
                return None
            
            instances = list(self._instances.values())
            if not instances:
                return None
            
            # Use simple round-robin based on current time
            idx = int(time.time()) % len(instances)
            return instances[idx]
    
    def is_model_available(self, model_name: str) -> bool:
        """Check if a model is available (running instance exists)."""
        return self.find_instance_by_name(model_name) is not None
    
    def get_common_models(self) -> List[str]:
        """Get list of common model families."""
        return self._common_models
    
    def get_model_info(self, family: str) -> Optional[Dict]:
        """Get detailed info about a model."""
        instance = self.get_instance(family)
        if not instance:
            return None
        
        return {
            "family": family,
            "port": instance.port,
            "host": instance.host,
            "status": instance.status,
            "last_used": instance.last_used,
        }


# Global router instance
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the global model router instance."""
    global _model_router
    if _model_router is None:
        raise RuntimeError("ModelRouter not initialized")
    return _model_router


def init_model_router(config_mgr, stats_service):
    """Initialize the global model router."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter(
            config_mgr=config_mgr,
            stats_service=stats_service,
        )
    return _model_router
