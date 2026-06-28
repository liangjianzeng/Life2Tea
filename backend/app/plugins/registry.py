"""
registry.py — Plugin discovery & registration.

Scans plugin directories for ``manifest.json`` files, parses them into
:class:`PluginManifest` objects, and exposes lookups by name / type / family.

This coexists with the legacy :class:`ModelRegistry` (which scans bare
``.gguf`` files). The bridge between them is :class:`ModelInfoAdapter`, which
projects a model-type plugin into the ``ModelInfo`` shape expected by
``models_router`` / ``chat_handler`` / ``routing``. Legacy GGUF scanning
remains as a fallback for users who have not yet authored manifests.

Typical use::

    reg = PluginRegistry(["plugins/models", "plugins/experts"])
    reg.discover()
    reg.list_plugins(type="model")
    reg.get("lfm2")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manifest import PluginManifest

log = logging.getLogger(__name__)


# ── Public descriptor ─────────────────────────────────────


@dataclass
class PluginDescriptor:
    """A discovered plugin: its manifest plus provenance."""
    manifest: PluginManifest
    source: str = "manifest"      # "manifest" | "gguf-fallback"
    errors: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def type(self) -> str:
        return self.manifest.type


# ── Registry ──────────────────────────────────────────────


class PluginRegistry:
    """Discovers and indexes plugins from one or more plugin roots.

    Args:
        roots: directories to scan (typically ["plugins/models",
            "plugins/experts"]). Non-existent dirs are silently skipped.
        env: extra environment variables for ``${VAR}`` expansion in
            manifests (merged over ``os.environ``).
    """

    MANIFEST_NAME = "manifest.json"

    def __init__(
        self,
        roots: Optional[List[str]] = None,
        *,
        env: Optional[Dict[str, str]] = None,
        repo_root: Optional[str] = None,
    ) -> None:
        self.roots = [Path(r) for r in (roots or [])]
        self.env: Dict[str, str] = dict(os.environ)
        if env:
            self.env.update(env)
        # repo_root defaults to two levels above backend/ (the project root).
        if repo_root:
            self._repo_root = Path(repo_root)
        else:
            self._repo_root = Path(__file__).resolve().parents[3]

        self._plugins: Dict[str, PluginDescriptor] = {}

    # ── discovery ──

    def discover(self) -> List[PluginDescriptor]:
        """Scan all roots and index manifests. Returns descriptors in scan order.
        Re-running replaces previously discovered plugins."""
        self._plugins.clear()
        found: List[PluginDescriptor] = []
        for root in self.roots:
            if not root.is_dir():
                log.debug("plugin root missing: %s", root)
                continue
            for manifest_path in sorted(root.rglob(self.MANIFEST_NAME)):
                desc = self._load_one(manifest_path)
                if desc:
                    # First manifest wins on name collision (stable ordering).
                    if desc.name not in self._plugins:
                        self._plugins[desc.name] = desc
                        found.append(desc)
                    else:
                        log.warning(
                            "duplicate plugin name %r in %s; keeping first",
                            desc.name, manifest_path,
                        )
        return found

    def _load_one(self, path: Path) -> Optional[PluginDescriptor]:
        try:
            mf = PluginManifest.from_file(path, env=self.env)
            mf.validate()
            log.info("discovered plugin %r (%s) at %s", mf.name, mf.type, path)
            return PluginDescriptor(manifest=mf, source="manifest")
        except Exception as e:  # never let one bad manifest abort discovery
            log.warning("skipping invalid manifest %s: %s", path, e)
            return PluginDescriptor(
                manifest=_BrokenManifest(path),
                source="manifest",
                errors=[str(e)],
            )

    # ── lookups ──

    def list_plugins(self, *, type: Optional[str] = None) -> List[PluginDescriptor]:
        out = list(self._plugins.values())
        if type:
            out = [d for d in out if d.type == type]
        return out

    def get(self, name: str) -> Optional[PluginDescriptor]:
        return self._plugins.get(name)

    def get_manifest(self, name: str) -> Optional[PluginManifest]:
        d = self._plugins.get(name)
        return d.manifest if d else None

    def names(self, *, type: Optional[str] = None) -> List[str]:
        return [d.name for d in self.list_plugins(type=type)]

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    # ── convenience: model family index ──

    def find_by_family(self, family: str) -> Optional[PluginDescriptor]:
        """Return the first model plugin whose model_family matches."""
        for d in self.list_plugins(type="model"):
            if d.manifest.model and d.manifest.model.model_family == family:
                return d
        return None

    # ── GGUF fallback ──

    def discover_with_gguf_fallback(
        self, models_dir: Optional[str] = None
    ) -> List[PluginDescriptor]:
        """Discover manifest plugins, then synthesize descriptors for bare
        ``.gguf`` files in *models_dir* that have no matching manifest.

        This keeps the system usable for users who haven't authored a manifest
        yet. A GGUF is matched to an existing manifest by family; unmatched
        files become lightweight model descriptors sourced ``gguf-fallback``.

        Args:
            models_dir: directory to scan for ``.gguf``. When None, no fallback
                is added and this is equivalent to :meth:`discover`.
        """
        self.discover()
        if not models_dir or not Path(models_dir).is_dir():
            return list(self._plugins.values())

        covered_families = {
            d.manifest.model.model_family
            for d in self.list_plugins(type="model")
            if d.manifest.model and d.manifest.model.model_family
        }

        for desc in self._scan_gguf(models_dir):
            # Skip GGUFs already covered by a real manifest (by family or name).
            if (
                desc.manifest.model
                and desc.manifest.model.model_family in covered_families
            ) or desc.name in self._plugins:
                continue
            self._plugins[desc.name] = desc
        return list(self._plugins.values())

    def _scan_gguf(self, models_dir: str) -> List[PluginDescriptor]:
        """Synthesize PluginDescriptors from bare .gguf files.

        Reuses the heuristics in :mod:`model_registry` (classify_family,
        detect_quantization, ...) so family inference stays consistent.
        """
        from .model_registry import (  # late import to avoid cycles
            classify_family, detect_quantization, detect_params_from_filename,
            FAMILY_PORTS, FAMILY_PARAMS, DEFAULT_PARAMS,
        )

        out: List[PluginDescriptor] = []
        root = Path(models_dir)
        for path in sorted(root.rglob("*.gguf")):
            if "mmproj" in path.name:
                continue
            name = path.stem
            family, display = classify_family(name)
            # Synthesize a minimal manifest dict and parse it.
            params = dict(DEFAULT_PARAMS)
            params.update(FAMILY_PARAMS.get(family, {}))
            raw = {
                "name": family,                 # key by family like _scan does
                "version": "0.0.0-auto",
                "type": "model",
                "display": display,
                "backend": "llama-cpp",
                "model_family": family,
                "model_path": str(path),
                "entry": {"runtime": "llama-server", "transport": "http"},
                "port": FAMILY_PORTS.get(family, 9090),
                "default_sampling_params": params,
            }
            try:
                mf = PluginManifest.from_dict(raw, env=self.env)
                out.append(PluginDescriptor(
                    manifest=mf, source="gguf-fallback",
                ))
            except Exception as e:
                log.warning("gguf fallback skip %s: %s", path, e)
        return out


# ── Bridge to legacy ModelInfo ────────────────────────────


@dataclass
class ModelInfoAdapter:
    """Projects a model-type plugin manifest into the legacy ``ModelInfo`` shape.

    This lets ``models_router`` / ``routing`` consume plugin data without a
    full rewrite. Fields mirror :class:`ModelRegistry.ModelInfo`.
    """

    family: str
    name: str
    display: str
    path: str
    size_gb: float
    quantization: str
    params_b: float
    default_port: int
    default_params: Dict[str, Any]
    manifest: PluginManifest

    @classmethod
    def from_manifest(cls, mf: PluginManifest) -> "ModelInfoAdapter":
        assert mf.model is not None, "model adapter requires a model manifest"
        m = mf.model
        sp = m.default_sampling_params
        return cls(
            family=m.model_family or mf.name,
            name=mf.name,
            display=mf.display or mf.name,
            path=m.model_path,
            size_gb=float(sp.get("size_gb", 0.0) or 0.0),
            quantization=str(sp.get("quantization", "") or ""),
            params_b=float(sp.get("params_b", 0.0) or 0.0),
            default_port=m.port,
            default_params=dict(sp),
            manifest=mf,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "family": self.family,
            "name": self.name,
            "display": self.display,
            "path": self.path,
            "size_gb": self.size_gb,
            "quantization": self.quantization,
            "params_b": self.params_b,
            "default_port": self.default_port,
            "default_params": self.default_params,
            "source": "plugin",
        }


# ── Broken-manifest placeholder ───────────────────────────


class _BrokenManifest:
    """Stand-in for an unparseable manifest so its name still indexes.

    Accessing typed fields raises; callers should check ``descriptor.errors``.
    """

    def __init__(self, path: Path) -> None:
        self.name = path.parent.name
        self.type = "unknown"
        self.manifest_path = str(path)

    def __getattr__(self, item: str) -> Any:
        raise AttributeError(
            f"manifest {self.name!r} failed to load; check descriptor.errors"
        )


__all__ = [
    "PluginRegistry",
    "PluginDescriptor",
    "ModelInfoAdapter",
]
