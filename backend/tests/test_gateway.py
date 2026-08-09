"""
test_gateway.py — tests for the Unified Model Gateway.

Covers ProviderSpec/Provider client, ProviderManager (discovery + routing),
GatewayRouter (task classification + fallback chain) and the OpenAI-compatible
router_api contract (non-streaming, without spawning real servers).
"""

import json
import os
import sys
import tempfile

import pytest

# Add backend directory to Python path (same approach as conftest.py)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def gateway_config(tmp_path):
    """Write a minimal gateway.json with three providers."""
    cfg = {
        "providers": {
            "lfm2": {
                "provider": "llamacpp",
                "model_path": "${MODELS_DIR}/lfm2.gguf",
                "host": "127.0.0.1",
                "port": 8082,
                "params": {"ctx_size": 32768, "n_gpu_layers": 99},
            },
            "qwen3.6": {
                "provider": "vllm",
                "model_name": "Qwen/Qwen3-6B",
                "host": "127.0.0.1",
                "port": 8083,
            },
            "glm": {
                "provider": "sglang",
                "model_name": "glm-4-9b",
                "host": "127.0.0.1",
                "port": 8088,
            },
        },
        "routing": {
            "code": ["qwen3.6", "lfm2"],
            "chat": ["lfm2", "qwen3.6"],
            "default": ["lfm2"],
        },
        "default_port_range": [8080, 8099],
        "default_host": "127.0.0.1",
        "llama_server_exe": "",
        "python": "python",
    }
    path = tmp_path / "gateway.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


class DummyConfigMgr:
    """Minimal ConfigManager stand-in exposing get_global()."""

    def __init__(self, models_dir=""):
        self._global = {"models_dir": models_dir, "llama_server_exe": "llama-server"}

    def get_global(self):
        return self._global


def test_provider_manager_discovers_endpoints(gateway_config):
    from app.gateway import ProviderManager

    manager = ProviderManager(config_path=gateway_config, config_mgr=DummyConfigMgr())
    endpoints = manager.list_endpoints()
    assert {e.name for e in endpoints} == {"lfm2", "qwen3.6", "glm"}
    lfm2 = manager.get_endpoint("lfm2")
    assert lfm2.spec.kind.value == "llamacpp"
    assert lfm2.port == 8082
    assert lfm2.spec.params["ctx_size"] == 32768


def test_gateway_router_task_classification_and_chain(gateway_config):
    from app.gateway import ProviderManager, GatewayRouter

    manager = ProviderManager(config_path=gateway_config, config_mgr=DummyConfigMgr())
    router = GatewayRouter(manager)

    assert router.classify_task([{"role": "user", "content": "帮我写一个 python 函数"}]) == "code"
    assert router.classify_task([{"role": "user", "content": "你好"}]) == "default"

    # Explicit preference always first
    chain = router.route_chain(
        messages=[{"role": "user", "content": "写代码"}],
        model_preference="glm",
    )
    names = [e.name for e in chain]
    assert names[0] == "glm"
    assert "lfm2" in names and "qwen3.6" in names

    # No preference → code rule candidates come first
    chain2 = router.route_chain([{"role": "user", "content": "写代码"}])
    assert chain2[0].name == "qwen3.6"


def test_router_api_list_models(gateway_config, monkeypatch):
    from app.gateway import ProviderManager
    from app.gateway.router_api import init_gateway, get_gateway

    manager = ProviderManager(config_path=gateway_config, config_mgr=DummyConfigMgr())
    gateway = init_gateway(manager)
    assert get_gateway() is gateway

    # Simulate the /v1/models handler logic
    data = []
    for e in manager.list_endpoints():
        data.append({"id": e.name, "object": "model", "owned_by": "life2tea", "status": e.status.value})
    assert {d["id"] for d in data} == {"lfm2", "qwen3.6", "glm"}


def test_provider_spec_launch_command_llamacpp(gateway_config):
    from app.gateway.providers.llamacpp import build_llamacpp_cmd
    from app.gateway import ProviderKind, ProviderSpec

    spec = ProviderSpec(
        name="lfm2", kind=ProviderKind.LLAMACPP,
        model_path="${MODELS_DIR}/lfm2.gguf", port=8082,
        params={"ctx_size": 32768, "n_gpu_layers": 99, "mmap": True},
    )
    cmd = build_llamacpp_cmd(spec, "llama-server", "C:/Models")
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "C:/Models/lfm2.gguf"
    assert "--ctx-size" in cmd and "32768" in cmd
    assert "--mmap" in cmd  # boolean flag without value
    assert "--port" in cmd and "8082" in cmd
