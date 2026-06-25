"""
router.py — System Router for MoE (Mixture-of-Experts) routing.

Implements Phase 1: Rule-Based Routing.
Later phases will add resource-aware and learned routing.
"""

import re
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import json


# Default routing rules (task_type -> ordered list of model plugins)
DEFAULT_RULES = {
    "code": ["lfm2"],
    "vision": ["lfm2"],
    "ocr": ["lfm2"],
    "math": ["lfm2"],
    "chat": ["lfm2"],
    "fast": ["lfm2"],
    "default": ["lfm2"],
}

# Keywords to detect task type from user message
TASK_KEYWORDS = {
    "code": [
        "代码", "编程", "函数", "def ", "class ", "import ", "python", "javascript",
        "code", "function", "class", "bug", "debug", "syntax", "algorithm",
        "写代码", "编程", "实现", "开发",
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


class SystemRouter:
    """
    Rule-based router that selects the best model plugin for a request.

    Phase 1: Simple keyword-based task classification + rule lookup.
    Phase 2 (TODO): Add resource awareness (GPU memory, model load status).
    Phase 3 (TODO): Replace with learned router (small ML model).
    """

    def __init__(self, rules: Optional[Dict[str, List[str]]] = None):
        self.rules = rules or DEFAULT_RULES.copy()
        self._config_file = Path("config/router_rules.json")

        # Try to load rules from config file
        if self._config_file.exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if "rules" in loaded:
                        self.rules = loaded["rules"]
            except Exception:
                pass

    def classify_task(self, messages: List[Dict[str, str]]) -> str:
        """
        Classify the task based on the last user message.
        Returns: task type string (e.g., "code", "vision", "chat")
        """
        if not messages:
            return "default"

        # Get the last user message
        last_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_msg = msg.get("content", "")
                break

        if not last_msg:
            return "default"

        # Check keywords for each task type
        last_msg_lower = last_msg.lower()
        for task_type, keywords in TASK_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in last_msg_lower:
                    return task_type

        return "default"

    def select_model(
        self,
        messages: List[Dict[str, str]],
        model_preference: Optional[str] = None,
        running_plugins: Optional[List[str]] = None,
    ) -> Tuple[str, str, int]:
        """
        Select the best model plugin for this request.

        Args:
            messages: Conversation messages
            model_preference: Explicit model request (from API body)
            running_plugins: List of currently running plugin names

        Returns:
            Tuple of (plugin_name, host, port) or raises RuntimeError
        """
        # If user explicitly requested a model, try to use it
        if model_preference:
            if running_plugins and model_preference in running_plugins:
                return model_preference, "127.0.0.1", 8080  # Port will be updated by caller
            # Even if not running, return it (caller will handle loading)

        # Classify task
        task_type = self.classify_task(messages)

        # Look up candidate models for this task
        candidates = self.rules.get(task_type, self.rules["default"])

        # Filter to running plugins if we have that info
        if running_plugins:
            for candidate in candidates:
                if candidate in running_plugins:
                    return candidate, "127.0.0.1", 8080  # Port updated by caller

        # No running plugin matches — return first candidate (caller handles loading)
        return candidates[0], "127.0.0.1", 8080

    def update_rules(self, new_rules: Dict[str, List[str]]) -> None:
        """Update routing rules and persist to config file."""
        self.rules.update(new_rules)
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_file, "w", encoding="utf-8") as f:
            json.dump({"rules": self.rules}, f, indent=2, ensure_ascii=False)

    def get_rules(self) -> Dict[str, List[str]]:
        """Return current routing rules."""
        return self.rules.copy()
