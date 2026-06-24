"""
backend_registry.py — GPU Backend Auto-Detection for Life2Tea

Migrated from LiangLLM/backend_selector.py.
Auto-detects available GPU backends for LLM inference runtimes.
Adapted for plugin architecture: backends are now plugins under plugins/backends/.
"""

import os
import subprocess
import platform
import shutil
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List


BACKEND_MAP = {
    "cuda":   {"dir": "llama-cpp-cuda",   "binary": "llama-server.exe",
               "extra_args": [], "label": "NVIDIA CUDA"},
    "vulkan": {"dir": "llama-cpp-vulkan", "binary": "llama-server.exe",
               "extra_args": [], "label": "Intel Vulkan"},
    "sycl":   {"dir": "llama-cpp-sycl",   "binary": "llama-server.exe",
               "extra_args": [], "label": "Intel SYCL"},
}


@dataclass
class BackendInfo:
    kind: str                        # "cuda" | "vulkan" | "sycl" | "cpu" | "custom"
    label: str                       # human-readable
    server_path: Optional[str]       # full path to llama-server.exe
    extra_args: list = field(default_factory=list)
    gpu_devices: list = field(default_factory=list)
    available: bool = False
    root_dir: Optional[str] = None


def _candidate_binary_names() -> List[str]:
    if platform.system() == "Windows":
        return ["llama-server.exe"]
    return ["llama-server", "server"]


def _is_executable(fpath: str) -> bool:
    if platform.system() == "Windows":
        return fpath.lower().endswith(".exe")
    return os.access(fpath, os.X_OK)


def _deep_find_server_under(root: str, max_depth: int = 4) -> List[str]:
    hits = []
    binary_names = _candidate_binary_names()
    if not os.path.isdir(root):
        return hits
    for cur, dirs, files in os.walk(root):
        rel = os.path.relpath(cur, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > max_depth:
            dirs[:] = []
            continue
        for fname in files:
            if fname in binary_names and _is_executable(os.path.join(cur, fname)):
                hits.append(os.path.join(cur, fname))
    return hits


def _guess_kind_from_path(path: str) -> str:
    p = path.lower()
    if "cuda" in p or "nvidia" in p:
        return "cuda"
    if "vulkan" in p or "arc" in p or "intel" in p:
        return "vulkan"
    if "sycl" in p:
        return "sycl"
    return "custom"


def _kind_label(kind: str) -> str:
    return {
        "cuda": "NVIDIA CUDA",
        "vulkan": "Intel Vulkan",
        "sycl": "Intel SYCL",
        "cpu": "CPU-only",
        "custom": "Custom (user-specified)",
    }.get(kind, "Unknown")


def _probe_gpu_devices(backend_dir: str) -> list:
    bench = os.path.join(backend_dir, "llama-bench.exe") if platform.system() == "Windows" \
        else os.path.join(backend_dir, "llama-bench")
    if not os.path.isfile(bench):
        return []
    try:
        result = subprocess.run(
            [bench, "--list-devices"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        devices = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if "ggml_vulkan:" in line and "=" in line:
                chunk = line.split("=", 1)[1].strip()
                if chunk:
                    devices.append(chunk)
            elif line.startswith("Vulkan") or line.startswith("CUDA"):
                devices.append(line)
            elif "MiB" in line and line:
                devices.append(line)
        return devices
    except Exception:
        return []


def _detect_nvidia_cuda() -> bool:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except Exception:
        return False


def scan_system_for_llama_servers() -> List[str]:
    """Best-effort broad scan: PATH + common install paths."""
    hits = []
    for name in _candidate_binary_names():
        p = shutil.which(name)
        if p:
            hits.append(os.path.abspath(p))

    if platform.system() == "Windows":
        roots = [
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            os.path.expanduser(r"~\scoop\apps"),
            os.path.expanduser(r"~\AppData\Local\Programs"),
            r"D:\tools", r"D:\apps", r"D:\llama", r"D:\LLM", r"D:\models",
            r"E:\tools", r"E:\apps", r"E:\LLM", r"E:\DTXY",
        ]
        for root in roots:
            if not os.path.isdir(root):
                continue
            found = _deep_find_server_under(root, max_depth=3)
            hits.extend(found)
    else:
        for root in ["/usr/local/bin", "/opt", os.path.expanduser("~")]:
            if os.path.isdir(root):
                hits.extend(_deep_find_server_under(root, max_depth=2))

    return list({os.path.abspath(h) for h in hits})


def detect_backend(
    project_root: str = None,
    user_llama_dir: str = "",
    user_server_exe: str = "",
    preference: str = "auto",
) -> BackendInfo:
    """Auto-detect the best available GPU backend."""
    if project_root is None:
        project_root = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(project_root)  # go up to backend/

    if user_server_exe and os.path.isfile(user_server_exe):
        return _build_from_exe(user_server_exe)

    if user_llama_dir:
        user_scan = _scan_user_dir(user_llama_dir)
        picked = _pick_by_preference(user_scan, preference)
        if picked:
            return picked

    if preference in ("auto", "cuda", "vulkan", "sycl"):
        if _detect_nvidia_cuda() and preference in ("auto", "cuda"):
            for backend_name in ["cuda"]:
                bdir = _find_backend_dir(project_root, BACKEND_MAP[backend_name]["dir"])
                if bdir is None:
                    continue
                info = BACKEND_MAP[backend_name]
                server = os.path.join(bdir, info["binary"])
                if os.path.isfile(server):
                    devices = _probe_gpu_devices(bdir)
                    return BackendInfo(
                        kind="cuda", label=info["label"],
                        server_path=server, extra_args=info["extra_args"],
                        gpu_devices=devices, available=True,
                        root_dir=bdir,
                    )
        for backend_name in ("vulkan", "sycl"):
            if preference != "auto" and preference != backend_name:
                continue
            bdir = _find_backend_dir(project_root, BACKEND_MAP[backend_name]["dir"])
            if bdir is None:
                continue
            info = BACKEND_MAP[backend_name]
            server = os.path.join(bdir, info["binary"])
            if os.path.isfile(server):
                devices = _probe_gpu_devices(bdir)
                return BackendInfo(
                    kind=backend_name, label=info["label"],
                    server_path=server, extra_args=info["extra_args"],
                    gpu_devices=devices, available=True,
                    root_dir=bdir,
                )

    sys_server_paths = scan_system_for_llama_servers()
    sys_scan = []
    for p in sys_server_paths:
        sys_scan.append(BackendInfo(
            kind=_guess_kind_from_path(p),
            label=_kind_label(_guess_kind_from_path(p)),
            server_path=p, available=True,
            extra_args=[], gpu_devices=_probe_gpu_devices(os.path.dirname(p)),
            root_dir=os.path.dirname(p),
        ))
    picked = _pick_by_preference(sys_scan, preference)
    if picked:
        return picked

    return BackendInfo(
        kind="cpu", label="CPU-only (llama-server not found)",
        server_path=None, available=False,
        extra_args=["-ngl", "0"],
    )


def _scan_user_dir(user_dir: str) -> List[BackendInfo]:
    results = []
    if not user_dir or not os.path.isdir(user_dir):
        return results
    found = _deep_find_server_under(user_dir, max_depth=5)
    for server_path in found:
        kind = _guess_kind_from_path(server_path)
        label = _kind_label(kind)
        devices = _probe_gpu_devices(os.path.dirname(server_path))
        results.append(BackendInfo(
            kind=kind, label=label,
            server_path=server_path, available=True,
            extra_args=[], gpu_devices=devices,
            root_dir=os.path.dirname(server_path),
        ))
    return results


def _find_backend_dir(project_root: str, subdir: str) -> Optional[str]:
    candidates = [
        os.path.join(project_root, "..", subdir),
        os.path.join(project_root, "..", "..", subdir),
        os.path.join(project_root, "backends", subdir),
    ]
    for c in candidates:
        abs_path = os.path.abspath(c)
        if os.path.isdir(abs_path):
            return abs_path
    return None


def _build_from_exe(exe_path: str) -> BackendInfo:
    if not exe_path or not os.path.isfile(exe_path):
        return BackendInfo(kind="custom", label="Custom", server_path=None, available=False)
    kind = _guess_kind_from_path(exe_path)
    label = _kind_label(kind)
    devices = _probe_gpu_devices(os.path.dirname(exe_path))
    return BackendInfo(
        kind=kind, label=label, server_path=os.path.abspath(exe_path),
        available=True, extra_args=[], gpu_devices=devices,
        root_dir=os.path.dirname(exe_path),
    )


def _pick_by_preference(infos: List[BackendInfo], preference: str) -> Optional[BackendInfo]:
    if not infos:
        return None
    if preference and preference != "auto":
        for info in infos:
            if info.kind == preference and info.available:
                return info
    priority = {"cuda": 0, "vulkan": 1, "sycl": 2, "custom": 3, "cpu": 4}
    infos_sorted = sorted(infos, key=lambda i: priority.get(i.kind, 99))
    for info in infos_sorted:
        if info.available:
            return info
    return None


def list_all_available_backends(
    project_root: str = None,
    user_llama_dir: str = "",
    user_server_exe: str = "",
) -> List[BackendInfo]:
    """List all backends found across all search locations."""
    if project_root is None:
        project_root = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(project_root)

    results: List[BackendInfo] = []
    seen = set()

    def _add(info: BackendInfo):
        if not info.server_path:
            return
        key = os.path.abspath(info.server_path).lower()
        if key in seen:
            return
        seen.add(key)
        results.append(info)

    if user_server_exe and os.path.isfile(user_server_exe):
        _add(_build_from_exe(user_server_exe))

    if user_llama_dir:
        for info in _scan_user_dir(user_llama_dir):
            _add(info)

    for kind, info in BACKEND_MAP.items():
        bdir = _find_backend_dir(project_root, info["dir"])
        if bdir is None:
            continue
        server = os.path.join(bdir, info["binary"])
        if os.path.isfile(server):
            devices = _probe_gpu_devices(bdir)
            _add(BackendInfo(
                kind=kind, label=info["label"],
                server_path=server, extra_args=info["extra_args"],
                gpu_devices=devices, available=True, root_dir=bdir,
            ))

    for p in scan_system_for_llama_servers():
        _add(BackendInfo(
            kind=_guess_kind_from_path(p),
            label=_kind_label(_guess_kind_from_path(p)),
            server_path=p, available=True,
            extra_args=[], gpu_devices=_probe_gpu_devices(os.path.dirname(p)),
            root_dir=os.path.dirname(p),
        ))

    priority = {"cuda": 0, "vulkan": 1, "sycl": 2, "custom": 3}
    results.sort(key=lambda i: priority.get(i.kind, 99))
    return results
