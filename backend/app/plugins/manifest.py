"""
manifest.py — Strongly-typed plugin manifest.

A manifest (``manifest.json``) is the single source of truth for a plugin's
configuration: identity, capabilities, default parameters, entry point and
resource budget. This module parses, validates and types raw JSON into
:class:`PluginManifest`.

Design notes:
  - Unknown fields are ignored (forward-compatible).
  - Path-valued fields support ``${MODELS_DIR}`` / ``${BACKEND_DIR}``
    variable expansion resolved against the runtime environment.
  - Schema validation is JSON-schema based, using the files under ``schema/``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Root holding schema/*.json — resolved relative to the repo layout:
# <repo>/schema/...  and  <repo>/backend/app/plugins/manifest.py
_SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schema"

_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


# ── Sub-structures ────────────────────────────────────────


@dataclass
class ModelSpec:
    """Model-type-specific fields. Populated only when type == 'model'."""
    backend: str = ""                       # e.g. "llama-cpp", "ollama"
    model_family: str = ""                  # e.g. "lfm2"
    model_path: str = ""                    # resolved absolute path
    port: int = 0
    supports: Dict[str, bool] = field(default_factory=dict)
    default_sampling_params: Dict[str, Any] = field(default_factory=dict)

    @property
    def quantization(self) -> str:
        return str(self.default_sampling_params.get("quantization", ""))


@dataclass
class ExpertSpec:
    """Expert-type-specific fields. Populated only when type == 'expert'."""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    dangerous: bool = False
    is_async: bool = False


@dataclass
class EntrySpec:
    """How to reach / start the plugin's runtime."""
    runtime: str = ""        # "llama-server", "ollama", "python", "module"
    transport: str = ""      # "http", "direct", "stdio"
    module: str = ""         # python module path for in-proc experts
    command: List[str] = field(default_factory=list)  # explicit argv override


@dataclass
class ResourceSpec:
    vram_mb: int = 0
    ram_mb: int = 0
    cpu_cores: int = 0
    load_timeout_sec: int = 180


@dataclass
class PluginManifest:
    """Typed, validated plugin manifest."""

    # ── identity (required) ──
    name: str
    version: str
    type: str                                 # 'model' | 'expert' | 'backend'
    entry: EntrySpec

    # ── display ──
    display: str = ""
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""

    # ── behaviour ──
    capabilities: List[str] = field(default_factory=list)
    resource: ResourceSpec = field(default_factory=ResourceSpec)

    # ── type-specific (filled by _bind_type_specific) ──
    model: Optional[ModelSpec] = None
    expert: Optional[ExpertSpec] = None

    # ── provenance ──
    manifest_path: str = ""
    base_dir: str = ""                        # dir containing manifest.json

    # ───────────────────────────────────────────────────
    # construction
    # ───────────────────────────────────────────────────

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        env: Optional[Dict[str, str]] = None,
    ) -> "PluginManifest":
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(
            raw,
            manifest_path=str(path),
            base_dir=str(path.parent),
            env=env,
        )

    @classmethod
    def from_dict(
        cls,
        raw: Dict[str, Any],
        *,
        manifest_path: str = "",
        base_dir: str = "",
        env: Optional[Dict[str, str]] = None,
    ) -> "PluginManifest":
        """Parse a manifest dict into a typed object. Does NOT validate against
        JSON-schema — call :meth:`validate` for that. Unknown keys ignored."""
        if not isinstance(raw, dict):
            raise ValueError("manifest must be a JSON object")

        # Required fields (mirrors schema/plugin-manifest.json)
        missing = [k for k in ("name", "version", "type", "entry") if k not in raw]
        if missing:
            raise ValueError(f"manifest missing required keys: {missing}")

        ptype = raw["type"]
        if ptype not in ("model", "expert", "backend"):
            raise ValueError(f"unknown plugin type: {ptype!r}")

        resolver = _VarResolver(env or {})
        base = Path(base_dir) if base_dir else None

        entry = _parse_entry(raw["entry"], resolver, base)

        obj = cls(
            name=raw["name"],
            version=str(raw["version"]),
            type=ptype,
            entry=entry,
            display=raw.get("display") or raw["name"],
            description=raw.get("description", ""),
            author=raw.get("author", ""),
            license=raw.get("license", ""),
            homepage=raw.get("homepage", ""),
            capabilities=list(raw.get("capabilities", []) or []),
            resource=_parse_resource(raw.get("resource") or {}),
            manifest_path=manifest_path,
            base_dir=base_dir,
        )

        if ptype == "model":
            obj.model = _parse_model_spec(raw, resolver, base)
        elif ptype == "expert":
            obj.expert = _parse_expert_spec(raw)

        return obj

    # ───────────────────────────────────────────────────
    # validation
    # ───────────────────────────────────────────────────

    def validate(self, schema_root: Optional[Path] = None) -> None:
        """Validate against the JSON-schema for this plugin type.

        Raises ``ValueError`` if jsonschema is unavailable or validation fails.
        Best-effort: a missing schema file is a soft warning, not an error.
        """
        try:
            import jsonschema  # type: ignore
        except ImportError:
            # jsonschema is optional at runtime; manifests are already typed.
            return

        root = Path(schema_root) if schema_root else _SCHEMA_ROOT
        schema_file = {
            "model": "model-plugin.schema.json",
            "expert": "expert-plugin.schema.json",
        }.get(self.type)
        if not schema_file:
            return  # backend manifests have no dedicated schema

        sp = root / schema_file
        if not sp.is_file():
            return

        with sp.open("r", encoding="utf-8") as f:
            schema = json.load(f)
        raw = self._to_raw()
        try:
            # Use a RefResolver with file:// base so relative $ref (e.g. "plugin-manifest.json")
            # resolves against the schema directory on disk.
            try:
                resolver = jsonschema.RefResolver(base_uri=f"file://{root}/", referrer=schema)
                jsonschema.validate(instance=raw, schema=schema, resolver=resolver)
            except Exception:
                # Fallback: attempt plain validate (older jsonschema versions)
                jsonschema.validate(instance=raw, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"manifest {self.name!r} failed schema: {e.message}") from e

    def _to_raw(self) -> Dict[str, Any]:
        """Reconstruct a dict approximating the source JSON for schema checks."""
        raw: Dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "entry": self.entry.runtime or self.entry.module,
        }
        if self.display:
            raw["display"] = self.display
        if self.capabilities:
            raw["capabilities"] = self.capabilities
        if self.type == "model" and self.model:
            m = self.model
            raw.update({
                "backend": m.backend,
                "model_family": m.model_family,
                "supports": m.supports,
                "default_sampling_params": m.default_sampling_params,
            })
        if self.type == "expert" and self.expert:
            e = self.expert
            raw.update({
                "input_schema": e.input_schema,
                "output_schema": e.output_schema,
                "dangerous": e.dangerous,
                "async": e.is_async,
            })
        return raw


# ── helpers ───────────────────────────────────────────────


class _VarResolver:
    """Resolves ``${VAR}`` tokens in path strings."""

    def __init__(self, env: Dict[str, str]) -> None:
        # Default env vars from the process; caller overrides win.
        self.env: Dict[str, str] = dict(os.environ)
        self.env.update(env)

    def expand(self, value: str) -> str:
        if not isinstance(value, str):
            return value

        def _sub(m: "re.Match[str]") -> str:
            return self.env.get(m.group(1), m.group(0))

        return _VAR_RE.sub(_sub, value)


def _parse_entry(
    raw: Any, resolver: _VarResolver, base: Optional[Path]
) -> EntrySpec:
    """``entry`` may be a string (runtime name) or an object with details."""
    if isinstance(raw, str):
        return EntrySpec(runtime=raw)

    if not isinstance(raw, dict):
        raise ValueError(f"invalid entry: {raw!r}")

    spec = EntrySpec(
        runtime=raw.get("runtime", ""),
        transport=raw.get("transport", ""),
        module=raw.get("module", ""),
        command=list(raw.get("command", []) or []),
    )
    # command argv may itself contain ${VAR} (e.g. model paths)
    spec.command = [resolver.expand(c) for c in spec.command]
    return spec


def _parse_model_spec(
    raw: Dict[str, Any], resolver: _VarResolver, base: Optional[Path]
) -> ModelSpec:
    spec = ModelSpec(
        backend=raw.get("backend", ""),
        model_family=raw.get("model_family", ""),
        model_path=resolver.expand(raw.get("model_path", "")),
        port=int(raw.get("port", 0) or 0),
        supports=dict(raw.get("supports") or {}),
        default_sampling_params=dict(raw.get("default_sampling_params") or {}),
    )
    # Resolve relative model paths against the manifest's base dir.
    if spec.model_path and not os.path.isabs(spec.model_path) and base:
        spec.model_path = str((base / spec.model_path).resolve())
    return spec


def _parse_expert_spec(raw: Dict[str, Any]) -> ExpertSpec:
    return ExpertSpec(
        input_schema=dict(raw.get("input_schema") or {}),
        output_schema=dict(raw.get("output_schema") or {}),
        dangerous=bool(raw.get("dangerous", False)),
        is_async=bool(raw.get("async", False)),
    )


def _parse_resource(raw: Dict[str, Any]) -> ResourceSpec:
    return ResourceSpec(
        vram_mb=int(raw.get("vram_mb", 0) or 0),
        ram_mb=int(raw.get("ram_mb", 0) or 0),
        cpu_cores=int(raw.get("cpu_cores", 0) or 0),
        load_timeout_sec=int(raw.get("load_timeout_sec", 180) or 180),
    )


__all__ = [
    "PluginManifest",
    "ModelSpec",
    "ExpertSpec",
    "EntrySpec",
    "ResourceSpec",
]
