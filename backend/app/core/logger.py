"""
logger.py — Life2Tea Log Archival and Query Manager

Migrated from LiangLLM/logger_manager.py.
Records backend logs, LLM lifecycle events, and supports filtered query,
deletion, archive export. Adapted for plugin architecture.
"""

import json
import os
import re
import shutil
import time
import zipfile
from collections import deque
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional


LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "FATAL")


class LoggerManager:
    def __init__(self, log_dir: str, retention_days: int = 30):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir = self.log_dir / "archive"
        self.archive_dir.mkdir(exist_ok=True)
        self.retention_days = retention_days
        self._buffer: deque = deque(maxlen=5000)
        self._last_flush = 0.0
        self._flush_interval = 2.0
        self._ensure_today()

    def _ensure_today(self):
        self.current_file = self.log_dir / f"{date.today().isoformat()}.log"
        if not self.current_file.exists():
            self.current_file.touch()

    def _today_file(self) -> Path:
        today = date.today().isoformat()
        p = self.log_dir / f"{today}.log"
        if not p.exists():
            p.touch()
        return p

    # ── Write API ─────────────────────────────────────────

    def write(
        self,
        level: str,
        module: str,
        message: str,
        model: str | None = None,
        plugin: str | None = None,
        extra: dict | None = None,
    ):
        level = (level or "INFO").upper()
        if level not in LEVELS:
            level = "INFO"
        entry = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "level": level,
            "module": module or "system",
            "message": (message or "").strip(),
            "model": model or "",
            "plugin": plugin or "",
            "extra": extra or {},
        }
        self._buffer.append(entry)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        try:
            self._today_file().open("a", encoding="utf-8").write(line)
        except Exception:
            pass
        self._maybe_flush()

    def _maybe_flush(self):
        now = time.monotonic()
        if now - self._last_flush > self._flush_interval:
            self._last_flush = now

    # ── Convenience helpers ───────────────────────────────

    def info(self, module, message, **kw):
        self.write("INFO", module, message, **kw)

    def warn(self, module, message, **kw):
        self.write("WARN", module, message, **kw)

    def error(self, module, message, **kw):
        self.write("ERROR", module, message, **kw)

    def debug(self, module, message, **kw):
        self.write("DEBUG", module, message, **kw)

    def fatal(self, module, message, **kw):
        self.write("FATAL", module, message, **kw)

    # ── File and date listing ──────────────────────────────

    def list_log_files(self, include_archive: bool = True):
        files = []
        for p in sorted(self.log_dir.glob("*.log"), reverse=True):
            files.append(self._file_info(p))
        if include_archive and self.archive_dir.exists():
            for p in sorted(self.archive_dir.glob("*.zip"), reverse=True):
                files.append(self._file_info(p, archived=True))
        return files

    def _file_info(self, path: Path, archived: bool = False) -> dict:
        stat = path.stat()
        name = path.name
        day = ""
        m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        if m:
            day = m.group(1)
        return {
            "name": name,
            "path": str(path),
            "day": day,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "archived": archived,
        }

    def list_days(self, include_archive: bool = True):
        days = []
        for p in self.log_dir.glob("*.log"):
            m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
            if m:
                days.append(m.group(1))
        if include_archive and self.archive_dir.exists():
            for p in self.archive_dir.glob("*.zip"):
                m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
                if m:
                    days.append(m.group(1))
        return sorted(set(days), reverse=True)

    # ── Query ──────────────────────────────────────────────

    def _read_file_lines(self, path: Path, max_lines: int = 20000):
        lines = []
        if not path.exists():
            return lines
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        lines.append(json.loads(line))
                    except Exception:
                        lines.append({
                            "ts": "", "level": "INFO", "module": "raw",
                            "message": line.strip(), "model": "", "plugin": "", "extra": {},
                        })
                    if len(lines) >= max_lines:
                        break
        except Exception:
            pass
        return lines

    def _iter_day_paths(self, date_from: str, date_to: str):
        paths = []
        start = datetime.strptime(date_from, "%Y-%m-%d").date()
        end = datetime.strptime(date_to, "%Y-%m-%d").date()
        cur = start
        while cur <= end:
            p = self.log_dir / f"{cur.isoformat()}.log"
            if p.exists():
                paths.append(p)
            cur = cur + timedelta(days=1)
        return paths

    def query(
        self,
        date_from: str,
        date_to: str | None = None,
        level: str | None = None,
        module: str | None = None,
        model: str | None = None,
        plugin: str | None = None,
        keyword: str | None = None,
        limit: int = 500,
        offset: int = 0,
        order: str = "asc",
    ):
        if not date_from:
            date_from = date.today().isoformat()
        if not date_to:
            date_to = date_from
        paths = self._iter_day_paths(date_from, date_to)
        all_entries = []
        for p in paths:
            all_entries.extend(self._read_file_lines(p))

        kw = keyword.strip().lower() if keyword else ""
        filtered = []
        for e in all_entries:
            if level and e.get("level") != level:
                continue
            if module and e.get("module") != module:
                continue
            if model and e.get("model") != model and e.get("module") != model:
                continue
            if plugin and e.get("plugin") != plugin:
                continue
            if kw:
                blob = " ".join([
                    str(e.get("message", "")),
                    str(e.get("module", "")),
                    str(e.get("level", "")),
                    str(e.get("model", "")),
                    str(e.get("plugin", "")),
                    json.dumps(e.get("extra", {}), ensure_ascii=False),
                ]).lower()
                if kw not in blob:
                    continue
            filtered.append(e)

        filtered.sort(key=lambda x: x.get("ts", ""), reverse=(order != "asc"))
        total = len(filtered)
        page = filtered[offset : offset + limit]

        # Return entries (not items) for frontend compatibility
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "entries": page,
            "levels": sorted({e.get("level") for e in page if e.get("level")}),
            "models": sorted({e.get("model") for e in page if e.get("model")}),
            "plugins": sorted({e.get("plugin") for e in page if e.get("plugin")}),
            "modules": sorted({e.get("module") for e in page if e.get("module")}),
        }

    # ── Summary ───────────────────────────────────────────

    def summary(self, days: int = 7):
        today = date.today()
        start = today - timedelta(days=days - 1)
        q = self.query(
            start.isoformat(), today.isoformat(),
            limit=10000, offset=0, order="asc",
        )
        items = q["entries"]

        # Build summary structure for frontend
        by_day = {}
        by_level = {}
        by_model = {}
        by_plugin = {}
        for e in items:
            day = (e.get("ts") or "")[:10] or "unknown"
            by_day[day] = by_day.get(day, 0) + 1
            by_level[e.get("level", "INFO")] = by_level.get(e.get("level", "INFO"), 0) + 1
            m = e.get("model") or "(none)"
            by_model[m] = by_model.get(m, 0) + 1
            p = e.get("plugin") or "(none)"
            by_plugin[p] = by_plugin.get(p, 0) + 1

        # Build days array (YYYY-MM-DD) for frontend
        days_array = []
        current = start
        for _ in range(days):
            day_str = current.isoformat()
            days_array.append({
                "date": day_str,
                "total": by_day.get(day_str, 0),
                "errors": by_level.get("ERROR", 0),
                "warnings": by_level.get("WARNING", 0),
            })
            current += timedelta(days=1)

        return {
            "days": days_array,
            "total": len(items),
            "by_level": by_level,
            "by_model": by_model,
            "by_plugin": by_plugin,
        }

    # ── Maintenance ───────────────────────────────────────

    def delete_day(self, day: str) -> bool:
        p = self.log_dir / f"{day}.log"
        if p.exists():
            p.unlink()
            return True
        return False

    def cleanup_before(self, days: int):
        cutoff = date.today() - timedelta(days=days)
        removed = []
        for p in list(self.log_dir.glob("*.log")):
            m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except Exception:
                continue
            if d < cutoff:
                p.unlink()
                removed.append(p.name)
        return {"removed": removed, "count": len(removed)}

    def archive_day(self, day: str, delete_source: bool = True):
        src = self.log_dir / f"{day}.log"
        if not src.exists():
            return {"ok": False, "error": f"log for {day} not found"}
        zip_path = self.archive_dir / f"{day}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(src, arcname=src.name)
        if delete_source:
            src.unlink()
        return {"ok": True, "zip": str(zip_path), "size": zip_path.stat().st_size}

    def archive_all_before(self, days: int, delete_source: bool = True):
        cutoff = date.today() - timedelta(days=days)
        done = []
        for p in list(self.log_dir.glob("*.log")):
            m = re.match(r"(\d{4}-\d{2}-\d{2})", p.name)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except Exception:
                continue
            if d < cutoff:
                res = self.archive_day(m.group(1), delete_source=delete_source)
                if res.get("ok"):
                    done.append(m.group(1))
        return {"archived": done, "count": len(done)}

    def read_raw(self, day: str, limit: int = 20000, offset: int = 0):
        p = self.log_dir / f"{day}.log"
        lines = self._read_file_lines(p, max_lines=limit + offset)
        return lines[offset : offset + limit]


# Singleton helpers (compatible with LiangLLM pattern)
_logger_manager: Optional[LoggerManager] = None


def get_logger_manager() -> LoggerManager:
    global _logger_manager
    if _logger_manager is None:
        raise RuntimeError("LoggerManager not initialized")
    return _logger_manager


def init_logger_manager(log_dir: str, retention_days: int = 30) -> LoggerManager:
    global _logger_manager
    _logger_manager = LoggerManager(log_dir, retention_days=retention_days)
    return _logger_manager
