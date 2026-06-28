"""
base.py — Plugin abstraction layer.

Defines the unified plugin contract for Life2Tea. Every plugin (model,
expert, backend) implements one of the interfaces below. Manifests drive
configuration; this module only defines *behaviour* contracts.

Plugin runtime models (decided at design time):
  - model  : sub-process (llama-server, ollama) + HTTP transport
  - expert : in-process Python module, direct calls
  - backend: non-loadable runtime declaration (llama-cpp, etc.)

See rfcs/001-pip-protocol.md for the protocol rationale.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from .manifest import PluginManifest


# ── Lifecycle ─────────────────────────────────────────────


class PluginState(str, Enum):
    """Lifecycle state of a loaded plugin instance."""
    DISCOVERED = "discovered"   # manifest found, never loaded
    LOADING = "loading"
    RUNNING = "running"
    UNLOADING = "unloading"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class PluginHealth:
    """Result of a health probe."""
    healthy: bool
    detail: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# ── Unified interface ─────────────────────────────────────


class IPlugin(ABC):
    """Base contract shared by every plugin.

    A plugin instance is created by its loader (see registry.py / lifecycle.py)
    and bound to a validated :class:`PluginManifest`. Concrete subclasses add
    type-specific behaviour (inference, tools, ...).
    """

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def plugin_type(self) -> str:
        return self.manifest.type

    @abstractmethod
    def load(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Acquire resources / start the runtime. Idempotent if already loaded."""

    @abstractmethod
    def unload(self) -> None:
        """Release resources / stop the runtime. Safe to call when not loaded."""

    @abstractmethod
    def health(self) -> PluginHealth:
        """Probe liveness. Must be cheap and never raise."""


class IModelPlugin(IPlugin):
    """Model plugin — sub-process backend serving an OpenAI-compatible API.

    Loaders are responsible for starting the backing process (e.g.
    llama-server.exe) and exposing its HTTP endpoint. Callers (chat_handler,
    routing) talk to the model purely over HTTP via :attr:`endpoint`.
    """

    @property
    @abstractmethod
    def endpoint(self) -> Tuple[str, int]:
        """(host, port) of the running model's HTTP server."""

    @abstractmethod
    async def infer(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Run a chat/completion request. Returns a dict (non-stream) or an
        async iterator of delta dicts (stream)."""


class IExpertPlugin(IPlugin):
    """Expert plugin — in-process tool provider (calculator, search, ...).

    Experts live inside the backend process, so a crash propagates. Keep
    experts to pure-compute work; anything touching external processes or
    the network belongs in a model plugin or a separate process.
    """

    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Declare tools in OpenAI function-calling schema."""

    @abstractmethod
    def execute(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one declared tool by name."""


__all__ = [
    "PluginState",
    "PluginHealth",
    "IPlugin",
    "IModelPlugin",
    "IExpertPlugin",
]
