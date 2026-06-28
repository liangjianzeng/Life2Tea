"""
inproc_loader.py — In-process plugin loader (expert plugins).

Loads Python-based expert plugins directly into the backend process.
Experts run in the same process as the backend, so they must be:
  - Pure Python (no subprocess calls)
  - Fast (blocking the main thread is bad)
  - Safe (no dangerous operations like file deletion)

If an expert needs to call external processes, use SubprocessRunner
instead and treat it as a model plugin.
"""

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .base import IExpertPlugin


@dataclass
class ExpertInstance:
    """Result of a successful expert load."""
    name: str
    plugin: IExpertPlugin
    module_path: str


class InprocLoader:
    """Loads expert plugins as Python modules."""

    def __init__(
        self,
        *,
        extra_search_paths: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            extra_search_paths: Additional directories to add to sys.path
            env: Environment variables (for config resolution)
        """
        self.extra_paths = [Path(p) for p in (extra_search_paths or [])]
        self.env = dict(os.environ)
        if env:
            self.env.update(env)

        # Prepend extra paths to sys.path (restored on unload)
        self._original_sys_path = list(sys.path)
        for p in self.extra_paths:
            if p.is_dir() and str(p) not in sys.path:
                sys.path.insert(0, str(p))

    def load(self, module_path: str, manifest_data: Optional[Dict[str, Any]] = None) -> ExpertInstance:
        """
        Load an expert plugin from a Python module path.

        Args:
            module_path: Dotted path like "app.plugins.experts.calculator"
            manifest_data: Optional manifest dict for plugin config

        Returns:
            ExpertInstance with loaded plugin instance

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If module doesn't export a Plugin subclass
        """
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"Failed to import module {module_path}: {e}")

        # Look for a Plugin subclass in the module
        plugin_class = self._find_plugin_class(module)
        if plugin_class is None:
            raise AttributeError(
                f"Module {module_path} has no IExpertPlugin subclass"
            )

        # Instantiate with manifest data as config
        config = manifest_data or {}
        plugin = plugin_class(**config)
        plugin.load()

        return ExpertInstance(
            name=plugin.manifest.name,
            plugin=plugin,
            module_path=module_path,
        )

    def _find_plugin_class(self, module) -> Optional[Type[IExpertPlugin]]:
        """Find the first IExpertPlugin subclass in module globals."""
        for obj in module.__dict__.values():
            if (
                isinstance(obj, type)
                and issubclass(obj, IExpertPlugin)
                and obj is not IExpertPlugin
            ):
                return obj
        return None

    def unload(self, instance: ExpertInstance) -> None:
        """Unload an expert instance and clean up."""
        try:
            instance.plugin.unload()
        except Exception:
            pass  # Best effort

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original sys.path
        sys.path.clear()
        sys.path.extend(self._original_sys_path)


__all__ = ["InprocLoader", "ExpertInstance"]


# ── Example expert plugin ───────────────────────────────────────────
# This is just a reference implementation. Real experts go in plugins/experts/

class _ExampleCalculatorPlugin(IExpertPlugin):
    """Example: a calculator expert that adds two numbers."""

    def __init__(self, **config):
        # Minimal manifest for demo
        from ..manifest import PluginManifest
        self.manifest = PluginManifest.from_dict({
            "name": "calculator",
            "version": "1.0.0",
            "type": "expert",
            "entry": {"runtime": "python"},
        })

    def load(self):
        pass

    def unload(self):
        pass

    def health(self) -> "PluginHealth":
        from ..base import PluginHealth
        return PluginHealth(healthy=True)

    def get_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two numbers",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }
        ]

    def execute(self, tool: str, args: dict) -> dict:
        if tool == "add":
            return {"result": args["a"] + args["b"]}
        raise ValueError(f"Unknown tool: {tool}")


if __name__ == "__main__":
    # Simple test
    loader = InprocLoader()
    try:
        instance = loader.load("__main__._ExampleCalculatorPlugin")
        tools = instance.plugin.get_tools()
        print(f"Loaded: {instance.name}, tools: {tools}")
        result = instance.plugin.execute("add", {"a": 2, "b": 3})
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
