"""
proxy_service.py — OpenAI-compatible Dynamic Model Proxy Service

A lightweight proxy server that:
- Provides OpenAI-compatible API on port 3003
- Dynamically loads/unloads models based on demand
- Implements LRU eviction strategy to manage GPU VRAM
- Uses llama.cpp as the inference engine

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    3003 端口 (FastAPI)                       │
    │  ┌────────────────────────────────────────────────────────┐  │
    │  │      OpenAI 兼容 API 代理层 (FastAPI)                   │  │
    │  │  - /v1/chat/completions                                 │  │
    │  │  - /v1/models                                           │  │
    │  │  - /v1/models/{id}/load                                 │  │
    │  │  - /v1/models/{id}/unload                               │  │
    │  │  - /health                                              │  │
    │  └────────────────────────────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────┘
                                │
                                ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                  动态模型加载与路由层                        │
    │  ┌────────────────────────────────────────────────────────┐  │
    │  │  模型管理器 (DynamicModelManager)                       │  │
    │  │  - 模型注册表 (支持 GGUF 格式)                          │  │
    │  │  - 动态模型加载/卸载                                    │  │
    │  │  - 资源监控 (GPU/VRAM)                                  │  │
    │  │  - LRU 驱逐策略                                         │  │
    │  └────────────────────────────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────┘
                                │
                                ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                 llama.cpp 后端进程层                         │
    │  ┌────────────────────────────────────────────────────────┐  │
    │  │  llama-server (每个模型独立进程)                        │  │
    │  │  - 8080-8999 端口范围 (动态分配)                        │  │
    │  └────────────────────────────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────┘
"""

import os
import sys
import json
import time
import threading
import subprocess
import httpx
import uvicorn
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────────────────
# 配置
# ────────────────────────────────────────────────────────────────────────

REMOTE_SERVER = "jianzengliang@100.81.83.59"
LLAMA_SERVER_EXE = "/home/jianzengliang/llama.cpp/build/bin/llama-server"
MODELS_DIR = "/home/jianzengliang/Models"
DEFAULT_PORT_RANGE = (8080, 8999)
MAX_VRAM_MB = 81920  # 80GB GPU
MAX_RAM_MB = 65536   # 64GB RAM


# ────────────────────────────────────────────────────────────────────────
# 数据结构
# ────────────────────────────────────────────────────────────────────────

class ModelStatus(str, Enum):
    PENDING = "pending"
    LOADING = "loading"
    RUNNING = "running"
    UNLOADING = "unloading"
    UNLOADED = "unloaded"
    ERROR = "error"


@dataclass
class ModelInstance:
    """Represents a running model instance."""
    model_name: str
    family: str
    port: int
    host: str = "127.0.0.1"
    status: str = ModelStatus.UNLOADED
    load_time: float = 0.0
    last_used: float = field(default_factory=time.time)
    request_count: int = 0
    pid: int = 0
    process: Optional[subprocess.Popen] = None
    log_file: str = ""
    
    def touch(self):
        """Update last used time."""
        self.last_used = time.time()
        self.request_count += 1
    
    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "family": self.family,
            "port": self.port,
            "host": self.host,
            "status": self.status,
            "load_time": self.load_time,
            "last_used": self.last_used,
            "request_count": self.request_count,
        }


# ────────────────────────────────────────────────────────────────────────
# GPU 监控工具
# ────────────────────────────────────────────────────────────────────────

def get_gpu_memory_mb() -> Dict[str, Any]:
    """Get GPU memory usage via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", 
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                parts = lines[0].split(",")
                return {
                    "used_mb": int(parts[0].strip()) if len(parts) > 0 else 0,
                    "total_mb": int(parts[1].strip()) if len(parts) > 1 else 0,
                    "utilization_percent": int(parts[2].strip()) if len(parts) > 2 else 0,
                }
    except Exception:
        pass
    return {"used_mb": 0, "total_mb": 0, "utilization_percent": 0}


# ────────────────────────────────────────────────────────────────────────
# 模型管理器
# ────────────────────────────────────────────────────────────────────────

class DynamicModelManager:
    """Manages dynamic model loading/unloading with LRU eviction."""
    
    def __init__(
        self,
        models_dir: str = MODELS_DIR,
        llama_server_exe: str = LLAMA_SERVER_EXE,
        port_range: tuple = DEFAULT_PORT_RANGE,
        max_vram_mb: int = MAX_VRAM_MB,
    ):
        self.models_dir = models_dir
        self.llama_server_exe = llama_server_exe
        self.port_range = port_range
        self.max_vram_mb = max_vram_mb
        
        self._instances: Dict[str, ModelInstance] = {}
        self._lock = threading.RLock()
        self._scan_models()
    
    def _scan_models(self):
        """Scan models directory and discover GGUF models + Ollama."""
        print(f"[ModelManager] Scanning models in {self.models_dir}", flush=True)

        # ── Discover Ollama models first ── (DISABLED - Ollama not installed)
        # self._discover_ollama_models()

        try:
            # List all GGUF files - use localhost since running on remote server
            cmd = f"ls -1 {self.models_dir}/*.gguf"
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                models = []
                for line in result.stdout.strip().split("\n"):
                    if line and line.endswith(".gguf"):
                        models.append(line.strip())

                print(f"[ModelManager] Found {len(models)} GGUF models", flush=True)

                # Extract model info from filename
                for model_path in models:
                    model_name = Path(model_path).stem
                    # Extract family from model name
                    family = model_name.lower()
                    if "qwen3.6" in family:
                        family = "qwen3.6"
                    elif "qwen3" in family:
                        family = "qwen3"
                    elif "glm" in family:
                        family = "glm"
                    elif "lfm" in family:
                        family = "lfm2"
                    elif "gemma" in family:
                        family = "gemma"
                    elif "vibe" in family:
                        family = "vibe"

                    # Assign default port based on family
                    default_port = self._get_default_port(family)

                    self._instances[model_name] = ModelInstance(
                        model_name=model_name,
                        family=family,
                        port=default_port,
                        status=ModelStatus.UNLOADED,
                    )

                print(f"[ModelManager] Discovered {len(self._instances)} models", flush=True)
        except Exception as e:
            print(f"[ModelManager] Error scanning models: {e}", flush=True)

    def _discover_ollama_models(self):
        """Discover available Ollama models and register them."""
        try:
            from ..plugins.ollama_plugin import get_ollama_models, DEFAULT_HOST, DEFAULT_PORT
            ollama_models = get_ollama_models()
            if ollama_models:
                print(f"[ModelManager] Found {len(ollama_models)} Ollama models", flush=True)
                for model_name in ollama_models:
                    # Use "ollama" as family for all Ollama models
                    self._instances[model_name] = ModelInstance(
                        model_name=model_name,
                        family="ollama",
                        port=DEFAULT_PORT,
                        host=DEFAULT_HOST,
                        status=ModelStatus.UNLOADED,
                    )
        except Exception as e:
            print(f"[ModelManager] Error discovering Ollama models: {e}", flush=True)

    def _is_ollama_model(self, instance: ModelInstance) -> bool:
        """Check if a model instance is an Ollama model."""
        return instance.family == "ollama"
    
    def _get_default_port(self, family: str) -> int:
        """Get default port for a model family."""
        # Simple hash-based port assignment within range
        port_hash = hash(family) % (self.port_range[1] - self.port_range[0] + 1)
        return self.port_range[0] + port_hash
    
    def _allocate_port(self) -> int:
        """Allocate an available port."""
        used_ports = {inst.port for inst in self._instances.values() 
                     if inst.status == ModelStatus.RUNNING}
        
        for port in range(self.port_range[0], self.port_range[1] + 1):
            if port not in used_ports:
                return port
        raise HTTPException(status_code=503, detail="No available ports")
    
    def _check_vram(self) -> bool:
        """Check if there's enough VRAM for loading a new model."""
        gpu_mem = get_gpu_memory_mb()
        return gpu_mem["used_mb"] < self.max_vram_mb
    
    def _evict_lru(self) -> Optional[ModelInstance]:
        """Evict the least recently used model."""
        with self._lock:
            running = [
                inst for inst in self._instances.values()
                if inst.status == ModelStatus.RUNNING
            ]
            
            if not running:
                return None
            
            # Sort by last_used time (oldest first)
            running.sort(key=lambda x: x.last_used)
            
            lru = running[0]
            print(f"[ModelManager] Evicting LRU model: {lru.model_name}", flush=True)
            
            self._unload_model_instance(lru)
            return lru
    
    def _ensure_vram(self):
        """Ensure there's enough VRAM by evicting models if needed."""
        while not self._check_vram():
            print(f"[ModelManager] VRAM low ({get_gpu_memory_mb()['used_mb']}MB), evicting...", flush=True)
            evicted = self._evict_lru()
            if not evicted:
                raise HTTPException(status_code=503, detail="VRAM insufficient and no models to evict")
    
    def _load_model_instance(self, instance: ModelInstance) -> bool:
        """Load a model instance — llama-server for GGUF, OllamaPlugin for ollama family."""
        print(f"[ModelManager] Loading model: {instance.model_name} (family={instance.family})", flush=True)

        if self._is_ollama_model(instance):
            return self._load_ollama_instance(instance)

        instance.status = ModelStatus.LOADING

        try:
            # Build command - run locally since we're on the remote server
            model_path = f"{self.models_dir}/{instance.model_name}.gguf"
            cmd = [
                self.llama_server_exe,
                "-m", model_path,
                "--port", str(instance.port),
                "--ctx-size", "262144",
                "--parallel", "2",
                "--n-gpu-layers", "99"
            ]

            # Execute command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            instance.pid = process.pid
            instance.process = process
            instance.load_time = time.time()
            instance.status = ModelStatus.LOADING

            # Wait for server to start (max 60s)
            for i in range(60):
                time.sleep(1)
                try:
                    import urllib.request
                    urllib.request.urlopen(
                        f"http://{instance.host}:{instance.port}/health",
                        timeout=2
                    )
                    instance.status = ModelStatus.RUNNING
                    print(f"[ModelManager] Model {instance.model_name} loaded successfully", flush=True)
                    return True
                except Exception:
                    pass

            # Timeout
            instance.status = ModelStatus.ERROR
            raise HTTPException(status_code=500, detail=f"Model {instance.model_name} failed to start")

        except Exception as e:
            instance.status = ModelStatus.ERROR
            print(f"[ModelManager] Failed to load {instance.model_name}: {e}", flush=True)
            raise

    def _load_ollama_instance(self, instance: ModelInstance) -> bool:
        """Load an Ollama model — connects to existing Ollama server."""
        import asyncio

        try:
            from ..plugins.ollama_plugin import OllamaPlugin

            manifest_data = {
                "name": instance.model_name,
                "version": "1.0.0",
                "type": "model",
                "display": f"Ollama:{instance.model_name}",
                "backend": "ollama",
                "model_family": "ollama",
            }

            from ..plugins.manifest import PluginManifest
            manifest = PluginManifest.from_dict(manifest_data)
            plugin = OllamaPlugin(manifest)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(plugin.load({"model": instance.model_name}))
            finally:
                loop.close()

            if not plugin._loaded:
                raise RuntimeError(f"Ollama model {instance.model_name} failed to load")

            ep_host, ep_port = plugin.endpoint
            instance.host = ep_host
            instance.port = ep_port
            instance.status = ModelStatus.RUNNING
            instance.load_time = time.time()
            instance._ollama_plugin = plugin  # type: ignore[attr-defined]

            print(
                f"[ModelManager] Ollama model {instance.model_name} ready at "
                f"{ep_host}:{ep_port}",
                flush=True,
            )
            return True

        except Exception as e:
            instance.status = ModelStatus.ERROR
            print(f"[ModelManager] Failed to load Ollama model {instance.model_name}: {e}", flush=True)
            raise
    
    def _unload_model_instance(self, instance: ModelInstance) -> bool:
        """Unload a model instance — kill process for GGUF, unload plugin for Ollama."""
        print(f"[ModelManager] Unloading model: {instance.model_name} (family={instance.family})", flush=True)

        if self._is_ollama_model(instance):
            return self._unload_ollama_instance(instance)

        instance.status = ModelStatus.UNLOADING

        try:
            if instance.process and instance.process.poll() is None:
                instance.process.terminate()
                try:
                    instance.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    instance.process.kill()

            instance.status = ModelStatus.UNLOADED
            instance.pid = 0
            instance.process = None
            print(f"[ModelManager] Model {instance.model_name} unloaded", flush=True)
            return True

        except Exception as e:
            print(f"[ModelManager] Failed to unload {instance.model_name}: {e}", flush=True)
            instance.status = ModelStatus.ERROR
            return False

    def _unload_ollama_instance(self, instance: ModelInstance) -> bool:
        """Unload an Ollama model — just mark as unloaded (server stays running)."""
        try:
            plugin = getattr(instance, "_ollama_plugin", None)
            if plugin is not None:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(plugin.unload())
                finally:
                    loop.close()

            instance.status = ModelStatus.UNLOADED
            print(f"[ModelManager] Ollama model {instance.model_name} unloaded", flush=True)
            return True
        except Exception as e:
            print(f"[ModelManager] Failed to unload Ollama model {instance.model_name}: {e}", flush=True)
            instance.status = ModelStatus.ERROR
            return False
    
    def get_model(self, model_name: str) -> Optional[ModelInstance]:
        """Get a model instance by name."""
        with self._lock:
            return self._instances.get(model_name)
    
    def list_models(self) -> List[dict]:
        """List all models with their status."""
        with self._lock:
            return [inst.to_dict() for inst in self._instances.values()]
    
    def load_model(self, model_name: str) -> dict:
        """Load a model dynamically."""
        with self._lock:
            instance = self._instances.get(model_name)
            if not instance:
                raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
            
            # Check if already running
            if instance.status == ModelStatus.RUNNING:
                instance.touch()
                return {"ok": True, "model": instance.to_dict(), "note": "already running"}
            
            # Ensure VRAM
            self._ensure_vram()
            
            # Allocate port if needed
            if instance.status == ModelStatus.UNLOADED:
                instance.port = self._allocate_port()
            
            # Load model
            success = self._load_model_instance(instance)
            if success:
                instance.touch()
                return {"ok": True, "model": instance.to_dict()}
            else:
                raise HTTPException(status_code=500, detail=f"Failed to load {model_name}")
    
    def unload_model(self, model_name: str) -> dict:
        """Unload a model."""
        with self._lock:
            instance = self._instances.get(model_name)
            if not instance:
                raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
            
            if instance.status != ModelStatus.RUNNING:
                return {"ok": True, "model": instance.to_dict(), "note": "not running"}
            
            self._unload_model_instance(instance)
            return {"ok": True, "model": instance.to_dict()}
    
    def chat_completions(self, model_name: str, messages: List[dict], **kwargs) -> dict:
        """Forward chat completions request to the model."""
        with self._lock:
            instance = self._instances.get(model_name)
            if not instance:
                raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
            
            # Auto-load if not running
            if instance.status != ModelStatus.RUNNING:
                self.load_model(model_name)
            
            instance.touch()
        
        # Forward to model
        return self._forward_request(instance, messages, **kwargs)
    
    def _forward_request(self, instance: ModelInstance, messages: List[dict], **kwargs) -> dict:
        """Forward request — OllamaPlugin for ollama family, HTTP proxy otherwise."""
        import uuid

        if self._is_ollama_model(instance):
            return self._forward_to_ollama(instance, messages, **kwargs)

        payload = {
            "model": instance.model_name,
            "messages": messages,
            **kwargs
        }

        try:
            import httpx
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"http://{instance.host}:{instance.port}/v1/chat/completions",
                    json=payload
                )
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Model request timeout")
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail=f"Cannot connect to model {instance.model_name}")

    def _forward_to_ollama(self, instance: ModelInstance, messages: List[dict], **kwargs) -> dict:
        """Forward request via OllamaPlugin."""
        import asyncio

        plugin = getattr(instance, "_ollama_plugin", None)
        if plugin is None:
            raise HTTPException(status_code=503, detail="Ollama plugin not loaded")

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                plugin.infer(messages, stream=False, **kwargs)
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ollama inference error: {e}")
        finally:
            loop.close()


# ────────────────────────────────────────────────────────────────────────
# FastAPI Router (OpenAI-compatible, no prefix for /v1/ endpoints)
# ────────────────────────────────────────────────────────────────────────

proxy_router = APIRouter(tags=["OpenAI Proxy"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stream: Optional[bool] = False
    stop: Optional[List[str]] = None


# Global model manager
_manager: Optional[DynamicModelManager] = None


def get_manager() -> DynamicModelManager:
    global _manager
    if _manager is None:
        _manager = DynamicModelManager()
    return _manager


@proxy_router.on_event("startup")
async def startup_event():
    global _manager
    _manager = DynamicModelManager()
    print(f"[ProxyService] Manager initialized with {_manager._instances} models", flush=True)


@proxy_router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "models_count": len(get_manager()._instances),
        "gpu": get_gpu_memory_mb(),
    }


@proxy_router.get("/v1/models")
async def list_models():
    """List all available models (OpenAI compatible)."""
    manager = get_manager()
    models = manager.list_models()
    
    return {
        "object": "list",
        "data": [
            {
                "id": m["model_name"],
                "object": "model",
                "created": int(m["load_time"]) if m["load_time"] else int(time.time()),
                "owned_by": "life2tea",
            }
            for m in models
        ],
    }


@proxy_router.post("/v1/models/{model_name}/load")
async def load_model(model_name: str):
    """Load a model dynamically."""
    manager = get_manager()
    return manager.load_model(model_name)


@proxy_router.post("/v1/models/{model_name}/unload")
async def unload_model(model_name: str):
    """Unload a model."""
    manager = get_manager()
    return manager.unload_model(model_name)


@proxy_router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint."""
    
    # Check if requested model is loaded
    manager = get_manager()
    model_name = req.model or list(manager._instances.keys())[0] if manager._instances else None
    
    if not model_name or model_name not in manager._instances:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model_name}' is not loaded. Please load it first via POST /v1/models/{model_name}/load"
        )
    
    instance = manager._instances[model_name]
    if instance.status != ModelStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model_name}' is not running (status: {instance.status.value}). Please load it first."
        )
    manager = get_manager()
    
    # Use provided model or default
    model_name = req.model or manager.list_models()[0]["model_name"] if manager.list_models() else None
    
    if not model_name:
        raise HTTPException(status_code=500, detail="No model available")
    
    # Forward request
    result = manager.chat_completions(model_name, [m.dict() for m in req.messages])
    
    return result


@proxy_router.get("/v1/models/{model_name}")
async def get_model(model_name: str):
    """Get model info."""
    manager = get_manager()
    instance = manager.get_model(model_name)
    
    if not instance:
        raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
    
    return instance.to_dict()


# ────────────────────────────────────────────────────────────────────────
# Server entry point (for standalone mode)
# ────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI

standalone_app = FastAPI(
    title="Life2Tea Dynamic Proxy",
    description="OpenAI-compatible dynamic model proxy with LRU eviction",
    version="1.0.0",
)
standalone_app.include_router(proxy_router)


def start_server(host: str = "0.0.0.0", port: int = 3003):
    """Start the proxy server."""
    print(f"[ProxyService] Starting on {host}:{port}", flush=True)
    uvicorn.run(standalone_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3003)
    args = parser.parse_args()
    
    start_server(host=args.host, port=args.port)
