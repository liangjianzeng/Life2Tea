"""
vllm.py — vLLM provider.

vLLM exposes an OpenAI-compatible server via
`python -m vllm.entrypoints.openai.api_server`. The launch command is built from
a ProviderSpec; the client is the shared generic `Provider` (all OpenAI-compatible).
"""

import os
import sys
from typing import List

from .base import Provider, ProviderKind, ProviderSpec

_PARAM_TO_FLAG = {
    "max_model_len": "--max-model-len",
    "gpu_memory_utilization": "--gpu-memory-utilization",
    "dtype": "--dtype",
    "enforce_eager": "--enforce-eager",
    "max_num_seqs": "--max-num-seqs",
    "max_num_batched_tokens": "--max-num-batched-tokens",
    "tensor_parallel_size": "--tensor-parallel-size",
    "served_model_name": "--served-model-name",
    "host": "--host",
    "port": "--port",
}


def build_vllm_cmd(spec: ProviderSpec, python: str = "python") -> List[str]:
    """Build the vLLM OpenAI-server launch command for a ProviderSpec."""
    cmd: List[str] = [python, "-m", "vllm.entrypoints.openai.api_server"]

    if spec.model_name:
        cmd += ["--model", spec.model_name]
    elif spec.model_path:
        cmd += ["--model", spec.model_path]

    cmd += ["--host", spec.host, "--port", str(spec.port)]

    for key, value in spec.params.items():
        flag = _PARAM_TO_FLAG.get(key, key.replace("_", "-"))
        if value is False or value is None:
            continue
        if value is True:
            cmd.append(f"--{flag.lstrip('-')}")
            continue
        cmd += [f"--{flag.lstrip('-')}", str(value)]

    return cmd


class VllmProvider(Provider):
    """Provider client for a vLLM OpenAI-compatible endpoint."""

    @staticmethod
    def kind() -> ProviderKind:
        return ProviderKind.VLLM
