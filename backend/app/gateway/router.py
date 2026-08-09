"""
router.py — GatewayRouter for the Unified Model Gateway.

Merges the old `SystemRouter` (keyword task classification + rule lookup) and the
load-balancing/fallback concerns of `ModelRouter` into a single router that
returns a *fallback chain* of candidate endpoints.
"""

from typing import Any, Dict, List, Optional

from .providers.base import EndpointStatus, ModelEndpoint
from .manager import ProviderManager

# Default routing rules (task_type -> ordered candidate endpoint names)
DEFAULT_RULES: Dict[str, List[str]] = {
    "code": [],
    "vision": [],
    "ocr": [],
    "math": [],
    "chat": [],
    "fast": [],
    "default": [],
}

# Keywords to classify the task from the latest user message
TASK_KEYWORDS: Dict[str, List[str]] = {
    "code": [
        "代码", "编程", "函数", "def ", "class ", "import ", "python", "javascript",
        "code", "function", "bug", "debug", "syntax", "algorithm",
        "写代码", "实现", "开发",
    ],
    "vision": [
        "图片", "图像", "照片", "识别", "ocr", "vision", "image", "photo", "picture",
        "看图片", "分析图片", "图片里", "图中",
    ],
    "math": [
        "数学", "计算", "方程", "积分", "导数", "math", "calculate", "equation",
        "算一下", "求解", "证明",
    ],
}


class GatewayRouter:
    """Routes requests to model endpoints, returning a fallback chain."""

    def __init__(self, manager: ProviderManager):
        self.manager = manager
        self._rules: Dict[str, List[str]] = dict(DEFAULT_RULES)
        self._rules.update(manager.get_routing())

    def refresh_rules(self) -> None:
        self._rules = dict(DEFAULT_RULES)
        self._rules.update(self.manager.get_routing())

    def update_rules(self, rules: Dict[str, List[str]]) -> None:
        self._rules.update(rules)
        self.manager.update_routing(self._rules)

    def get_rules(self) -> Dict[str, List[str]]:
        return self._rules.copy()

    def classify_task(self, messages: List[Dict[str, str]]) -> str:
        """Return a task type for the latest user message (keyword-based)."""
        if not messages:
            return "default"
        last_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_msg = msg.get("content", "")
                break
        if not last_msg:
            return "default"
        lower = last_msg.lower()
        for task_type, keywords in TASK_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in lower:
                    return task_type
        return "default"

    def _running(self, name: str) -> Optional[ModelEndpoint]:
        endpoint = self.manager.get_endpoint(name)
        if endpoint and endpoint.status == EndpointStatus.RUNNING:
            return endpoint
        return None

    def route_chain(
        self,
        messages: Optional[List[Dict[str, str]]] = None,
        model_preference: Optional[str] = None,
    ) -> List[ModelEndpoint]:
        """
        Build an ordered fallback chain of candidate endpoints.

        Priority:
          1. Explicit `model_preference` (if configured) — always first
          2. Task-classified rule candidates (running first, then configured)
          3. Any currently-running endpoints as a safety net
          4. Any configured endpoint as a last resort
        """
        candidates: List[str] = []

        if model_preference:
            candidates.append(model_preference)

        task = self.classify_task(messages or []) if messages else "default"
        rule_candidates = self._rules.get(task, self._rules["default"])
        for name in rule_candidates:
            if name not in candidates:
                candidates.append(name)

        # Safety nets
        for endpoint in self.manager.list_endpoints():
            if endpoint.name not in candidates:
                candidates.append(endpoint.name)

        chain: List[ModelEndpoint] = []
        for name in candidates:
            endpoint = self.manager.get_endpoint(name)
            if endpoint and endpoint not in chain:
                chain.append(endpoint)
        return chain

    def select(
        self,
        messages: Optional[List[Dict[str, str]]] = None,
        model_preference: Optional[str] = None,
    ) -> Optional[ModelEndpoint]:
        """
        Select the best currently-running endpoint (no fallback).
        Used by internal /api/chat path.
        """
        chain = self.route_chain(messages, model_preference)
        for endpoint in chain:
            if endpoint.status == EndpointStatus.RUNNING:
                return endpoint
        # Nothing running — return the first configured endpoint so caller can auto-load
        for endpoint in chain:
            return endpoint
        return None
