"""
llamacpp.py — llama.cpp (llama-server) provider.

Builds the subprocess launch command for a llama-server endpoint from a
ProviderSpec. Absorbs the old `DynamicModelManager._load_model_instance` and
`model_registry.build_server_args` logic.
"""

import os
from typing import List

from .base import Provider, ProviderKind, ProviderSpec


# llama-server sampling/run flags that map 1:1 from spec.params
_PARAM_TO_FLAG = {
    "ctx_size": "--ctx-size",
    "n_gpu_layers": "--n-gpu-layers",
    "threads": "--threads",
    "batch_size": "--batch-size",
    "ubatch_size": "--ubatch-size",
    "parallel": "--parallel",
    "top_k": "--top-k",
    "top_p": "--top-p",
    "temperature": "--temp",
    "repeat_penalty": "--repeat-penalty",
    "mirostat": "--mirostat",
    "flash_attn": "--flash-attn",
    "cont_batching": "--cont-batching",
    "mmap": "--mmap",
    "mlock": "--mlock",
    "spec_type": "--spec-type",
    "model_draft": "--model-draft",
    "draft_parallel": "--draft-parallel",
    "draft_n": "--draft-n",
    "draft_min_tokens": "--draft-min-tokens",
}


def build_llamacpp_cmd(spec: ProviderSpec, server_exe: str, models_dir: str) -> List[str]:
    """Build the llama-server launch command for a ProviderSpec."""
    cmd: List[str] = [server_exe]

    # Resolve model path (support ${MODELS_DIR} expansion)
    model_path = spec.model_path
    model_path = model_path.replace("${MODELS_DIR}", models_dir)
    if not model_path and spec.model_name:
        # model_name acts as the GGUF filename inside models_dir
        model_path = os.path.join(models_dir, f"{spec.model_name}.gguf")
    if model_path:
        cmd += ["-m", model_path]

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


class LlamaCppProvider(Provider):
    """Provider client for a llama-server endpoint."""

    @staticmethod
    def kind() -> ProviderKind:
        return ProviderKind.LLAMACPP
