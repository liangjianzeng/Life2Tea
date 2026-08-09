"""
sglang.py — SGLang provider.

SGLang exposes an OpenAI-compatible server via
`python -m sglang.launch_server`. The launch command is built from a
ProviderSpec; the client is the shared generic `Provider`.
"""

from typing import List

from .base import Provider, ProviderKind, ProviderSpec

_PARAM_TO_FLAG = {
    "max_model_len": "--max-model-len",
    "mem_fraction_static": "--mem-fraction-static",
    "tp_size": "--tp",
    "dtype": "--dtype",
    "cuda_graph_max_batch_size": "--cuda-graph-max-batch-size",
    "quant": "--quant",
    "enable_mixed_quant": "--enable-mixed-quant",
    "speculative_algorithm": "--speculative-algorithm",
    "speculative_num_draft_tokens": "--speculative-num-draft-tokens",
    "host": "--host",
    "port": "--port",
}


def build_sglang_cmd(spec: ProviderSpec, python: str = "python") -> List[str]:
    """Build the SGLang launch-server command for a ProviderSpec."""
    cmd: List[str] = [python, "-m", "sglang.launch_server"]

    if spec.model_name:
        cmd += ["--model-path", spec.model_name]
    elif spec.model_path:
        cmd += ["--model-path", spec.model_path]

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


class SglangProvider(Provider):
    """Provider client for an SGLang OpenAI-compatible endpoint."""

    @staticmethod
    def kind() -> ProviderKind:
        return ProviderKind.SGLANG
