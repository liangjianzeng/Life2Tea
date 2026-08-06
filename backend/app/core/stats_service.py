import re
"""
stats_service.py — System Statistics Service

Provides comprehensive statistics collection and analysis for system monitoring.
"""

import psutil
import sqlite3
import subprocess
import platform
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import threading
import time
import json

from .database import Database



# --- model display name helpers (added 2026-08-06) ---------------------------
# GGUF 文件名 → 可读模型名。规则：去扩展名 / 去分片编号 / 从右往左剥离
# 量化、格式、打包标记 token，遇到第一个「非丢弃类」token 即停止，
# 避免误伤 Ornith-1.0-35B-MTP-APEX-I-Balanced 这类含大写标记的正式名字。
_SHARD_RE = re.compile(r"[-_]\d{3,6}[-_]of[-_]\d{3,6}$", re.I)
_DROP_TOKEN_RES = [
    re.compile(r"^UD$", re.I),                       # Unsloth Dynamic 前缀
    re.compile(r"^I?Q\d[A-Z0-9_]*$", re.I),          # Q4_K_M / IQ2_M / Q8_0 / IQ3_XXS
    re.compile(r"^(BF16|F16|F32|FP16|FP32)$", re.I),  # 浮点格式
    re.compile(r"^(MX|NV)FP\d[A-Z0-9_]*$", re.I),     # MXFP4_MOE / NVFP4
    re.compile(r"^(mtp|imatrix|imat|gguf)$", re.I),   # 打包标记
]


def _is_drop_token(tok: str) -> bool:
    return any(r.match(tok) for r in _DROP_TOKEN_RES)


def _clean_model_name(path_or_name):
    """把 GGUF 路径/文件名规整成模型名；失败时返回原始 basename。"""
    if not path_or_name:
        return None
    raw = str(path_or_name).replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"\.gguf$", "", raw, flags=re.I)
    name = _SHARD_RE.sub("", name)
    parts = name.split("-")
    while len(parts) > 1 and _is_drop_token(parts[-1]):
        parts.pop()
    cleaned = "-".join(parts).strip("-_ ")
    return cleaned or raw


def _display_model_name(alias, model_path):
    """alias 若已是有意义的别名（非路径）则直接用，否则清洗文件路径。"""
    if alias and "/" not in str(alias) and not str(alias).lower().endswith(".gguf"):
        return str(alias)
    return _clean_model_name(model_path)
# ---------------------------------------------------------------------------



# ── 投机解码（speculative decoding）类型检测 ─────────────────────────────
# 判定依据是 llama-server 的启动命令行，而不是发探测请求看 timings.draft_n：
#   * 命令行是权威来源，100% 准确，零开销；
#   * 探测请求在服务繁忙时会排进 llama.cpp 任务队列直接超时，导致误判为"关"。
_SPEC_LABELS = {
    "draft-mtp": "MTP",
    "draft-dspark": "DSpark",
    "draft-eagle": "EAGLE",
    "draft-eagle3": "EAGLE3",
    "draft-medusa": "Medusa",
    "draft-lookahead": "Lookahead",
    "draft-ngram": "N-gram",
    "draft-model": "草稿模型",
}
_SPEC_OFF = {"", "none", "off", "no", "disabled", "0"}


def _detect_spec(cmd) -> dict:
    """从 llama-server 命令行解析投机解码配置。"""
    spec_type = None
    draft_model = None
    n_max = None
    cmd = list(cmd or [])
    for i, a in enumerate(cmd):
        if a == "--spec-type" and i + 1 < len(cmd):
            spec_type = cmd[i + 1]
        elif a.startswith("--spec-type="):
            spec_type = a.split("=", 1)[1]
        elif a in ("-md", "--model-draft") and i + 1 < len(cmd):
            draft_model = cmd[i + 1]
        elif a.startswith("--model-draft="):
            draft_model = a.split("=", 1)[1]
        elif a in ("--spec-draft-n-max", "--draft-max", "--draft-n-max", "--draft") and i + 1 < len(cmd):
            try:
                n_max = int(cmd[i + 1])
            except (ValueError, TypeError):
                pass
        elif a.startswith(("--spec-draft-n-max=", "--draft-max=", "--draft=")):
            try:
                n_max = int(a.split("=", 1)[1])
            except (ValueError, TypeError):
                pass

    st = (spec_type or "").strip().lower()
    if st and st not in _SPEC_OFF:
        label = _SPEC_LABELS.get(st)
        if not label:
            # 未知类型：去掉 draft- 前缀后大写，例如 draft-foo -> FOO
            label = re.sub(r"^draft[-_]", "", st).upper() or st
        kind = st
        enabled = True
    elif draft_model:
        # 只给了 -md 没给 --spec-type：经典 draft-model 投机
        kind, label, enabled = "draft-model", "草稿模型", True
    else:
        kind, label, enabled = None, None, False

    return {
        "enabled": enabled,
        "kind": kind,
        "label": label,
        "n_max": n_max,
        "draft_model": (os.path.basename(draft_model) if draft_model else None),
    }


class StatsService:
    """System statistics service"""

    def __init__(self, db: Database):
        self.db = db
        # Initialize disk IO baseline so the first rate poll is meaningful
        self._last_disk_io = {
            "time": datetime.now(),
            "read_bytes": 0,
            "write_bytes": 0,
        }
        # Initialize network baseline for rate calculation
        self._last_net_io = {
            "time": datetime.now(),
            "bytes_sent": 0,
            "bytes_recv": 0,
        }

    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect current system metrics"""
        vmem = psutil.virtual_memory()
        net = psutil.net_io_counters()

        # Disk IO counters (cumulative)
        disk_io = psutil.disk_io_counters()
        now = datetime.now()

        disk_io_values = {"read_bytes": 0, "write_bytes": 0, "read_rate": 0.0, "write_rate": 0.0}
        if disk_io:
            disk_io_values["read_bytes"] = disk_io.read_bytes
            disk_io_values["write_bytes"] = disk_io.write_bytes
            if self._last_disk_io:
                elapsed = (now - self._last_disk_io["time"]).total_seconds()
                if elapsed > 0:
                    disk_io_values["read_rate"] = (disk_io.read_bytes - self._last_disk_io["read_bytes"]) / elapsed
                    disk_io_values["write_rate"] = (disk_io.write_bytes - self._last_disk_io["write_bytes"]) / elapsed
        self._last_disk_io = {"time": now, "read_bytes": disk_io_values["read_bytes"], "write_bytes": disk_io_values["write_bytes"]}

        # Calculate network throughput rates
        now_net = datetime.now()
        net_rate_sent = 0.0
        net_rate_recv = 0.0
        if self._last_net_io:
            elapsed_net = (now_net - self._last_net_io["time"]).total_seconds()
            if elapsed_net > 0:
                net_rate_sent = (net.bytes_sent - self._last_net_io["bytes_sent"]) / elapsed_net
                net_rate_recv = (net.bytes_recv - self._last_net_io["bytes_recv"]) / elapsed_net
        self._last_net_io = {"time": now_net, "bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv}

        metrics = {
            "cpu": psutil.cpu_percent(interval=0.1),
            "memory": {
                "total": vmem.total,
                "used": vmem.used,
                "percent": vmem.percent,
            },
            "disk": {
                "total": psutil.disk_usage('/').total,
                "used": psutil.disk_usage('/').used,
                "percent": psutil.disk_usage('/').percent,
            },
            "disk_io": disk_io_values,
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
                "rate_sent": net_rate_sent,
                "rate_recv": net_rate_recv,
            },
            "timestamp": now.isoformat(),
            "gpu": None,
        }

        # NVIDIA GPU monitoring
        try:
            result = subprocess.run(
                ['nvidia-smi',
                 '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                 '--format=csv,nounits,noheader'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split('\n')[0].split(', ')
                # Handle [N/A] values
                def safe_float(val):
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return None

                def safe_int(val):
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        return None

                metrics["gpu"] = {
                    "utilization": safe_float(parts[0]),
                    "memory_used": safe_float(parts[1]),
                    "memory_total": safe_float(parts[2]),
                    "temperature_c": safe_int(parts[3]),
                }
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            metrics["gpu"] = None

        return metrics

    def _now_iso(self) -> str:
        return datetime.now().isoformat()

    # ── Persistence ─────────────────────────────────────

    def _record_system_metrics(self, m: Dict[str, Any]):
        """Persist a single metrics snapshot to DB."""
        conn = self.db.get_connection()
        try:
            # Ensure disk_io columns exist (migration from older schema)
            self._ensure_disk_io_columns(conn)
            conn.execute("""
                INSERT INTO system_metrics
                (timestamp, cpu_usage, memory_total, memory_used, memory_percent,
                 disk_total, disk_used, disk_percent,
                 network_bytes_sent, network_bytes_recv,
                 disk_io_read_bytes, disk_io_write_bytes, disk_io_read_rate, disk_io_write_rate,
                 gpu_utilization, gpu_memory_used, gpu_memory_total, gpu_temperature)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                m["timestamp"],
                m["cpu"],
                m["memory"]["total"],
                m["memory"]["used"],
                m["memory"]["percent"],
                m["disk"]["total"],
                m["disk"]["used"],
                m["disk"]["percent"],
                m["network"]["bytes_sent"],
                m["network"]["bytes_recv"],
                m.get("disk_io", {}).get("read_bytes", 0),
                m.get("disk_io", {}).get("write_bytes", 0),
                m.get("disk_io", {}).get("read_rate", 0),
                m.get("disk_io", {}).get("write_rate", 0),
                m["gpu"]["utilization"] if m["gpu"] else None,
                m["gpu"]["memory_used"] if m["gpu"] else None,
                m["gpu"]["memory_total"] if m["gpu"] else None,
                m["gpu"]["temperature_c"] if m["gpu"] else None,
            ))
            conn.commit()
        finally:
            conn.close()

    def record_request(self, method: str, path: str, status_code: int,
                       response_time: float, client_ip: str, timestamp: str):
        """Record a request stat."""
        conn = self.db.get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO request_stats
                   (timestamp, method, path, status_code, response_time, client_ip)
                   VALUES (?,?,?,?,?,?)""",
                (timestamp, method, path, status_code, response_time, client_ip)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # ── Dashboard & stats ───────────────────────────────

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Return combined dashboard data."""
        return {
            "stats": self._summary_stats(),
            "timestamp": self._now_iso(),
        }

    def get_system_metrics(self) -> Dict[str, Any]:
        """Return current live metrics."""
        return self.collect_system_metrics()

    # ── Resource usage history ──────────────────────────

    def _range_start(self, range_str: str) -> str:
        """Return ISO-start for a range like 1h, 6h, 24h, today, 7d, 30d."""
        now = datetime.now()
        if range_str in ("1h",):
            return (now - timedelta(hours=1)).isoformat()
        elif range_str in ("6h",):
            return (now - timedelta(hours=6)).isoformat()
        elif range_str in ("24h", "today"):
            return now.replace(hour=0, minute=0, second=0).isoformat()
        elif range_str in ("7d", "week"):
            return (now - timedelta(days=7)).isoformat()
        elif range_str in ("30d", "month"):
            return (now - timedelta(days=30)).isoformat()
        return (now - timedelta(hours=1)).isoformat()

    def get_resource_usage(self, range_str: str = "1h") -> Dict[str, Any]:
        """Return hourly resource usage over the given range."""
        start = self._range_start(range_str)
        end = self._now_iso()
        conn = self.db.get_connection()
        try:
            # Check if disk_io columns exist
            has_disk_io = False
            try:
                conn.execute("SELECT disk_io_read_rate FROM system_metrics")
                has_disk_io = True
            except sqlite3.OperationalError:
                pass

            if has_disk_io:
                cur = conn.execute(
                    """SELECT timestamp, cpu_usage, memory_used, memory_total,
                              gpu_utilization, gpu_memory_used, gpu_memory_total, gpu_temperature,
                              disk_io_read_rate, disk_io_write_rate
                       FROM system_metrics
                       WHERE timestamp >= ? AND timestamp <= ?
                       ORDER BY timestamp""",
                    (start, end)
                )
                rows = cur.fetchall()
                result = []
                for r in rows:
                    gpu = None
                    if r[4] is not None:
                        gpu = {
                            "utilization": r[4],
                            "memory_used": r[5],
                            "memory_total": r[6],
                            "temperature_c": r[7],
                        }
                    result.append({
                        "timestamp": r[0],
                        "cpu": r[1],
                        "memory": {"used": r[2], "total": r[3]},
                        "gpu": gpu,
                        "disk_io": {
                            "read_rate": r[8] or 0,
                            "write_rate": r[9] or 0,
                        },
                    })
            else:
                cur = conn.execute(
                    """SELECT timestamp, cpu_usage, memory_used, memory_total,
                              gpu_utilization, gpu_memory_used, gpu_memory_total, gpu_temperature
                       FROM system_metrics
                       WHERE timestamp >= ? AND timestamp <= ?
                       ORDER BY timestamp""",
                    (start, end)
                )
                rows = cur.fetchall()
                result = []
                for r in rows:
                    gpu = None
                    if r[4] is not None:
                        gpu = {
                            "utilization": r[4],
                            "memory_used": r[5],
                            "memory_total": r[6],
                            "temperature_c": r[7],
                        }
                    result.append({
                        "timestamp": r[0],
                        "cpu": r[1],
                        "memory": {"used": r[2], "total": r[3]},
                        "gpu": gpu,
                    })
            return {"data": result}
        finally:
            conn.close()

    # ── Performance metrics ─────────────────────────────

    def get_performance_metrics(self, range_str: str = "1h") -> Dict[str, Any]:
        """Return latency percentiles."""
        start = self._range_start(range_str)
        end = self._now_iso()
        conn = self.db.get_connection()
        try:
            cur = conn.execute(
                """SELECT COUNT(*), AVG(response_time), MAX(response_time),
                          MIN(response_time),
                          SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END),
                          SUM(CASE WHEN status_code < 400 THEN 1 ELSE 0 END)
                   FROM request_stats
                   WHERE timestamp >= ? AND timestamp <= ?""",
                (start, end)
            )
            row = cur.fetchone()
            total = row[0] or 0
            avg_rt = row[1] or 0
            max_rt = row[2] or 0
            min_rt = row[3] or 0
            errors = row[4] or 0
            successes = row[5] or 0

            # Percentiles
            pct_rows = conn.execute(
                """SELECT response_time FROM request_stats
                   WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY response_time""",
                (start, end)
            ).fetchall()
            rts = [r[0] for r in pct_rows]

            def pct(data, p):
                if not data:
                    return 0
                idx = int(len(data) * p)
                return data[min(idx, len(data) - 1)]

            return {
                "data": [
                    {"label": "P50 (Median)", "value": round(pct(rts, 0.50), 2)},
                    {"label": "P95", "value": round(pct(rts, 0.95), 2)},
                    {"label": "P99", "value": round(pct(rts, 0.99), 2)},
                ],
                "summary": {
                    "total": total,
                    "avg_response_time": round(avg_rt, 2),
                    "max_response_time": round(max_rt, 2),
                    "min_response_time": round(min_rt, 2),
                    "error_count": errors,
                    "success_count": successes,
                },
            }
        finally:
            conn.close()

    # ── API key stats ───────────────────────────────────

    def get_api_key_stats(self, key_id: Optional[int] = None,
                          range_str: str = "today") -> Dict[str, Any]:
        """Aggregate usage per API key."""
        # Use raw SQL — api_keys table has TEXT id, we join by name
        start = self._range_start(range_str)
        end = self._now_iso()
        conn = self.db.get_connection()
        try:
            cur = conn.execute(
                """SELECT
                      ak.name,
                      COUNT(*) as request_count,
                      AVG(rs.response_time) as avg_response_time
                   FROM api_key_usage aku
                   JOIN api_keys ak ON aku.key_id = CAST(ak.id AS INTEGER)
                   JOIN request_stats rs ON aku.request_id = rs.id
                   WHERE aku.timestamp >= ? AND aku.timestamp <= ?
                   GROUP BY ak.id, ak.name
                   ORDER BY request_count DESC""",
                (start, end)
            )
            rows = cur.fetchall()
            keys = []
            for r in rows:
                keys.append({
                    "name": r[0],
                    "request_count": r[1],
                    "avg_response_time": round(r[2], 2) if r[2] else 0,
                    "last_used_at": None,
                })

            # Try to get last_used from api_keys table directly
            if key_id is None:
                cur2 = conn.execute(
                    "SELECT id, name, last_used_at FROM api_keys ORDER BY last_used_at DESC LIMIT 20"
                )
                last_used_map = {}
                for r2 in cur2.fetchall():
                    last_used_map[r2[1]] = r2[2]
                for k in keys:
                    lu = last_used_map.get(k["name"])
                    k["last_used_at"] = datetime.fromtimestamp(lu).isoformat() if lu else None

            return {"data": keys}
        finally:
            conn.close()

    # ── Recent logs ─────────────────────────────────────

    def get_logs(self, level: Optional[str] = None,
                 limit: int = 50) -> Dict[str, Any]:
        """Return recent request logs from DB (as simple system logs)."""
        conn = self.db.get_connection()
        try:
            query = """SELECT timestamp, method, path, status_code, response_time, client_ip
                       FROM request_stats WHERE 1=1"""
            params = []

            if level:
                if level == "ERROR":
                    query += " AND status_code >= 400"
                elif level == "WARNING":
                    query += " AND status_code >= 400"
                elif level == "DEBUG":
                    pass  # include all

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cur = conn.execute(query, params)
            rows = cur.fetchall()

            result = []
            for r in rows:
                status = r[3]
                if status >= 500:
                    lvl = "ERROR"
                elif status >= 400:
                    lvl = "WARNING"
                else:
                    lvl = "INFO"
                result.append({
                    "timestamp": r[0],
                    "level": lvl,
                    "module": f"{r[1]} {r[2]}",
                    "message": f"Status {status} — {r[4]:.1f}ms",
                })
            return {"data": result}
        finally:
            conn.close()

    # ── Placeholder methods ─────────────────────────────

    def get_api_key_detail(self, key_id: Optional[str] = None,
                           limit: int = 50) -> Dict[str, Any]:
        """Get detailed request history for an API key."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT rs.timestamp, rs.method, rs.path, rs.status_code,
                       rs.response_time, rs.client_ip
                FROM request_stats rs
                JOIN api_key_usage aku ON rs.id = aku.request_id
                JOIN api_keys ak ON aku.key_id = CAST(ak.id AS INTEGER)
            """
            params = []

            if key_id:
                query += " WHERE ak.id = ?"
                params.append(key_id)

            query += " ORDER BY rs.timestamp DESC LIMIT ?"
            params.append(limit)

            cur = conn.execute(query, params)
            rows = cur.fetchall()

            result = []
            for r in rows:
                status = r[3]
                if status >= 500:
                    lvl = "ERROR"
                elif status >= 400:
                    lvl = "WARNING"
                else:
                    lvl = "INFO"
                result.append({
                    "timestamp": r[0],
                    "method": r[1],
                    "path": r[2],
                    "status_code": r[3],
                    "response_time": r[4],
                    "client_ip": r[5],
                    "level": lvl,
                })
            return {"data": result}
        finally:
            conn.close()

    def get_token_usage(self, time_range: str = "today") -> Dict[str, Any]:
        """Get token usage statistics."""
        conn = self.db.get_connection()
        try:
            # Calculate time range
            end_time = datetime.now()
            if time_range == "today":
                start_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
            elif time_range == "week":
                start_time = end_time - timedelta(days=7)
            elif time_range == "month":
                start_time = end_time - timedelta(days=30)
            else:
                start_time = end_time - timedelta(days=1)

            start_str = start_time.isoformat()
            end_str = end_time.isoformat()

            # Get token usage
            query = """
                SELECT
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output,
                    model_family,
                    model_name
                FROM token_usage
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY model_family, model_name
            """
            cursor = conn.execute(query, (start_str, end_str))
            rows = cursor.fetchall()

            total_input = sum(r[0] or 0 for r in rows)
            total_output = sum(r[1] or 0 for r in rows)

            by_model = {}
            for row in rows:
                model = row[2] or "unknown"
                if model not in by_model:
                    by_model[model] = {"input": 0, "output": 0, "family": row[3]}
                by_model[model]["input"] += row[0] or 0
                by_model[model]["output"] += row[1] or 0

            return {
                "period": time_range,
                "data": {
                    "total_input_tokens": total_input,
                    "total_output_tokens": total_output,
                    "by_model": by_model,
                }
            }
        except Exception as e:
            print(f"Error getting token usage: {e}")
            return {"period": time_range, "data": {"total_input_tokens": 0, "total_output_tokens": 0, "by_model": {}}}
        finally:
            conn.close()

    # ── Live llama.cpp server metrics (process discovery) ──
    _MODEL_METRICS_PREV = {}
    _MTP_CACHE = {}  # {port: {"ts": float, "mtp": dict, "pid": int}}
    _PROBE_TOKENS = {}  # {port: {"ts": float, "pred": int, "prompt": int}}

    _PROMPT_TOK_S_SAMPLES = {}  # {port: [(ts, prompt_tok_s), ...]}
    _TOK_S_SAMPLES = {}  # {port: [(ts:float, tok_s:float), ...]} pruned to last 60s
    _PEAK_STORE_PATH = "/tmp/life2tea_model_metrics_peak.json"

    def _http_get_text(self, url: str, timeout: int = 3) -> str:
        import urllib.request
        req = urllib.request.Request(url, headers={"Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def _http_get_json(self, url: str, timeout: int = 3):
        import json as _json
        return _json.loads(self._http_get_text(url, timeout))

    def _parse_llamacpp_metrics(self, text: str) -> dict:
        import re as _re
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "{" in line or "\"" in line:
                continue
            m = _re.match(r"^([A-Za-z_:]+)\s+([-\d.eE+]+)$", line)
            if m:
                try:
                    result[m.group(1)] = float(m.group(2))
                except ValueError:
                    pass
        return result

    def _apply_parsed_metrics(self, entry: dict, parsed: dict, port: int) -> None:
        """填充当前速率 + 累计总量。

        取值优先级（预填充 / 解码同理）：
          1) llama.cpp 原生速率 gauge —— llamacpp:prompt_tokens_seconds 与
             llamacpp:predicted_tokens_seconds。这是 llama.cpp 内部按真实请求
             计时算出的平均速率，比我们自己差分更准，也不受探测请求污染。
          2) counter 差分（tokens_total / seconds_total 的窗口增量）作为兜底，
             用于个别 build 不导出 gauge 的情况。
          3) 若本轮无新增流量（空闲），回退到持久化的最近一次有效值(sticky)，
             使仪表盘长期显示数值，而不是一空闲就归零/消失。
        """
        import time as _t

        prev = StatsService._MODEL_METRICS_PREV.get(port)
        pred = parsed.get("llamacpp:tokens_predicted_total")
        pred_sec = parsed.get("llamacpp:tokens_predicted_seconds_total")
        prompt = parsed.get("llamacpp:prompt_tokens_total")
        prompt_sec = parsed.get("llamacpp:prompt_seconds_total")

        # llama.cpp 自带的速率 gauge（首选数据源）
        gauge_pred = parsed.get("llamacpp:predicted_tokens_seconds")
        gauge_prompt = parsed.get("llamacpp:prompt_tokens_seconds")

        # 扣掉后端自身探测请求产生的 token，避免空闲服务被探测“刷”出速率
        _now = _t.time()
        rec = StatsService._PROBE_TOKENS.get(port)
        _in = bool(rec and prev and prev.get("ts", 0) < rec["ts"] <= _now)
        _probe_pred = rec.get("pred", 0) if _in else 0
        _probe_prompt = rec.get("prompt", 0) if _in else 0

        # ── 解码速率 ──
        tok_s = 0.0
        if gauge_pred and gauge_pred > 0:
            tok_s = float(gauge_pred)
        elif prev and "pred" in prev and "pred_sec" in prev and pred is not None and pred_sec is not None:
            dp = pred - prev["pred"] - _probe_pred
            ds = pred_sec - prev["pred_sec"]
            if dp > 0 and ds > 0:
                tok_s = dp / ds

        # ── 预填充速率 ──
        prompt_tok_s = 0.0
        if gauge_prompt and gauge_prompt > 0:
            prompt_tok_s = float(gauge_prompt)
        elif prev and "prompt" in prev and "prompt_sec" in prev and prompt is not None and prompt_sec is not None:
            dp = prompt - prev["prompt"] - _probe_prompt
            ds = prompt_sec - prev["prompt_sec"]
            if dp > 0 and ds > 0:
                prompt_tok_s = dp / ds

        # ── sticky 回退：空闲窗口保留最近一次有效观测 ──
        tok_s = StatsService._sticky_rate(port, "tok_s", tok_s)
        prompt_tok_s = StatsService._sticky_rate(port, "prompt_tok_s", prompt_tok_s)

        entry["tok_s"] = tok_s
        entry["prompt_tok_s"] = prompt_tok_s
        entry["total_prompt_tokens"] = prompt
        entry["total_predicted_tokens"] = pred

        peak_tok, peak_prompt = StatsService._record_peak(port, tok_s, prompt_tok_s)
        entry["tok_s_peak"] = peak_tok
        entry["prompt_tok_s_peak"] = peak_prompt

        StatsService._MODEL_METRICS_PREV[port] = {
            "ts": _now, "pred": pred, "pred_sec": pred_sec,
            "prompt": prompt, "prompt_sec": prompt_sec,
        }

    @classmethod
    def _sticky_rate(cls, port: int, key: str, value):
        """速率 sticky：本轮有值就记录并返回；本轮为 0（空闲）则返回上次有效值。

        持久化到 /tmp 的峰值文件，因此 uvicorn --reload 重启进程后仍然保留。
        """
        try:
            store = cls._load_peak_store()
            p = store.setdefault(str(port), {})
            k = "cur_" + key
            if value and value > 0:
                p[k] = float(value)
                cls._save_peak_store(store)
                return float(value)
            return float(p.get(k) or 0.0)
        except Exception:
            return float(value or 0.0)

    @classmethod
    def _record_peak(cls, port: int, tok_s, prompt_tok_s):
        """滚动 300s 峰值。

        与旧实现的关键差别：窗口内没有样本时**不再返回 None**，而是回退到持久化的
        last-known 峰值。旧行为会让前端 v-if="prompt_tok_s_peak != null" 判空，
        把整块“预填充”文字隐藏 —— 这正是“一会有一会没有”的直接原因。
        """
        import time as _t
        now = _t.time()
        store = cls._load_peak_store()
        p = store.setdefault(str(port), {"tok_s": [], "prompt_tok_s": []})

        if tok_s and tok_s > 0:
            p.setdefault("tok_s", []).append([now, tok_s])
            p["last_tok_s"] = [now, float(tok_s)]
        if prompt_tok_s and prompt_tok_s > 0:
            p.setdefault("prompt_tok_s", []).append([now, prompt_tok_s])
            p["last_prompt_tok_s"] = [now, float(prompt_tok_s)]

        p["tok_s"] = [[ts, v] for ts, v in p.get("tok_s", []) if ts > now - 300]
        p["prompt_tok_s"] = [[ts, v] for ts, v in p.get("prompt_tok_s", []) if ts > now - 300]

        peak_tok = max((v for _, v in p["tok_s"]), default=None)
        peak_prompt = max((v for _, v in p["prompt_tok_s"]), default=None)

        # 窗口过期 -> 回退到最近一次观测到的峰值，保证长期可见
        if peak_tok is None:
            _lt = p.get("last_tok_s")
            if _lt and _lt[1] > 0:
                peak_tok = _lt[1]
        if peak_prompt is None:
            _lp = p.get("last_prompt_tok_s")
            if _lp and _lp[1] > 0:
                peak_prompt = _lp[1]

        cls._save_peak_store(store)
        return peak_tok, peak_prompt

    @classmethod
    def _load_peak_store(cls):
        try:
            with open(cls._PEAK_STORE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def _save_peak_store(cls, store):
        try:
            tmp = cls._PEAK_STORE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(store, f)
            os.replace(tmp, cls._PEAK_STORE_PATH)
        except Exception:
            pass


    def _probe_server(self, port: int) -> dict:
        import json as _json, urllib.request, time as _time

        def _counter(name):
            try:
                txt = self._http_get_text(f"http://127.0.0.1:{port}/metrics", timeout=8)
                return self._parse_llamacpp_metrics(txt).get(name)
            except Exception:
                return None

        pre_pred = _counter("llamacpp:tokens_predicted_total")
        pre_prompt = _counter("llamacpp:prompt_tokens_total")
        payload = _json.dumps({
            "prompt": "Reply with the single word: ok",
            "n_predict": 64,
            "temperature": 0,
            "cache_prompt": True,
        }).encode("utf-8")
        _t0 = _time.time()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/completion",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            d = _json.loads(r.read().decode("utf-8", "replace"))
        _elapsed = _time.time() - _t0
        post_pred = _counter("llamacpp:tokens_predicted_total")
        post_prompt = _counter("llamacpp:prompt_tokens_total")
        _pred_delta = (post_pred - pre_pred) if (pre_pred is not None and post_pred is not None) else 0
        _prompt_delta = (post_prompt - pre_prompt) if (pre_prompt is not None and post_prompt is not None) else 0
        if _pred_delta < 0:
            _pred_delta = 0
        if _prompt_delta < 0:
            _prompt_delta = 0
        _probe_tok_s = (_pred_delta / _elapsed) if (_elapsed > 0 and _pred_delta > 0) else 0.0
        _probe_prompt_tok_s = (_prompt_delta / _elapsed) if (_elapsed > 0 and _prompt_delta > 0) else 0.0
        StatsService._PROBE_TOKENS[port] = {
            "ts": _time.time(), "pred": int(_pred_delta), "prompt": int(_prompt_delta)
        }
        t = d.get("timings") or {}
        draft_n = t.get("draft_n")
        draft_accepted = t.get("draft_n_accepted")
        mtp = {"enabled": False, "acceptance": None, "drafted": None, "accepted": None}
        if draft_n and draft_n > 0:
            mtp = {
                "enabled": True,
                "acceptance": (draft_accepted / draft_n) if draft_accepted is not None else None,
                "drafted": draft_n,
                "accepted": draft_accepted,
            }
        _tn = t.get("predicted_n"); _tms = t.get("predicted_ms")
        _pn = t.get("prompt_n"); _pms = t.get("prompt_ms")
        _ts_timing = (_tn / (_tms / 1000.0)) if (_tn and _tms and _tms > 0) else 0.0
        _pts_timing = (_pn / (_pms / 1000.0)) if (_pn and _pms and _pms > 0) else 0.0
        _final_tok_s = _ts_timing if _ts_timing > 0 else _probe_tok_s
        _final_prompt_tok_s = _pts_timing if _pts_timing > 0 else _probe_prompt_tok_s
        return {
            "tok_s": _final_tok_s,
            "prompt_tok_s": _final_prompt_tok_s,
            "mtp": mtp,
        }

    def get_model_metrics(self) -> Dict[str, Any]:
        """Discover running llama.cpp servers and sample live metrics.

        Discovery is process-based: we scan live llama-server processes,
        resolve each one's listening port, then sample tok/s + MTP acceptance.
        Passive /metrics (when started with --metrics) is preferred; otherwise
        a short probe completion is used.
        """
        import time
        servers = []
        seen_ports = set()
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    info = proc.info
                    cmd = info.get("cmdline") or []
                except Exception:
                    continue
                if not cmd:
                    continue
                cmd_str = " ".join(cmd)
                if not ("llama-server" in cmd_str or "llama.cpp/build/bin" in cmd_str):
                    continue
                pid = info.get("pid")
                port = None
                for i, a in enumerate(cmd):
                    if a in ("--port", "-p", "--grpc-port") and i + 1 < len(cmd):
                        try:
                            port = int(cmd[i + 1])
                        except ValueError:
                            pass
                    elif a.startswith("--port="):
                        try:
                            port = int(a.split("=", 1)[1])
                        except ValueError:
                            pass
                if port is None:
                    try:
                        for c in proc.net_connections(kind="tcp"):
                            if getattr(c, "status", None) == "LISTEN" and c.laddr:
                                port = c.laddr.port
                                break
                    except Exception:
                        pass
                if port is None or port in seen_ports:
                    continue
                seen_ports.add(port)

                entry = {
                    "pid": pid,
                    "port": port,
                    "model": None,
                    "model_path": None,
                    "rss_memory_bytes": None,
                    "tok_s": None,
                    "prompt_tok_s": None,
                    "total_prompt_tokens": None,
                    "total_predicted_tokens": None,
                    "kv_cache_used": None,
                    "kv_cache_total": None,
                    "mtp": {"enabled": False, "acceptance": None,
                            "drafted": None, "accepted": None},
                    "spec": {"enabled": False, "kind": None, "label": None,
                             "n_max": None, "draft_model": None},
                    "source": None,
                    "alive": True,
                    "error": None,
                }

                # 投机解码类型：命令行是权威来源（MTP / DSpark / 草稿模型）
                try:
                    _sp = _detect_spec(cmd)
                    entry["spec"] = _sp
                    entry["mtp"]["enabled"] = _sp["enabled"]
                except Exception:
                    pass

                try:
                    mi = proc.memory_info()
                    entry["rss_memory_bytes"] = getattr(mi, "rss", None)
                except Exception:
                    pass

                try:
                    m = self._http_get_json(f"http://127.0.0.1:{port}/v1/models")
                    models = (m or {}).get("models") or []
                    if models:
                        entry["model_path"] = models[0].get("model") or models[0].get("name")
                        # 优先用启动时 -a/--alias 指定的别名（若有），否则从文件名清洗模型名
                        alias = None
                        for i, a in enumerate(cmd):
                            if a in ("-a", "--alias") and i + 1 < len(cmd):
                                alias = cmd[i + 1]
                            elif a.startswith("--alias="):
                                alias = a.split("=", 1)[1]
                        entry["model"] = _display_model_name(alias, entry["model_path"])
                except Exception:
                    for i, a in enumerate(cmd):
                        if a in ("--model", "-m") and i + 1 < len(cmd):
                            entry["model_path"] = cmd[i + 1]
                            entry["model"] = _clean_model_name(cmd[i + 1])
                        elif a.startswith("--model="):
                            entry["model_path"] = a.split("=", 1)[1]
                            entry["model"] = _clean_model_name(entry["model_path"])

                metrics_text = None
                try:
                    metrics_text = self._http_get_text(f"http://127.0.0.1:{port}/metrics", timeout=8)
                except Exception:
                    metrics_text = None

                if metrics_text and "Not Implemented" not in metrics_text and "not supported" not in metrics_text:
                    parsed = self._parse_llamacpp_metrics(metrics_text)
                    self._apply_parsed_metrics(entry, parsed, port)
                    entry["source"] = "metrics"
                    # MTP acceptance is sampled ONCE per server lifecycle (see the
                    # unified block below) — no periodic probe here. The live tok/s
                    # + rolling peak above come purely from real /metrics traffic, so
                    # an idle server correctly reads 0 and the peak reflects genuine
                    # bursts only.
                else:
                    # No /metrics endpoint: mark probe-only. The one-time MTP probe
                    # (unified block below) seeds tok_s_peak + mtp on first
                    # discovery; we do NOT poll this server on a timer.
                    entry["source"] = "probe"
                    # best-effort cumulative totals even in probe-only mode
                    try:
                        _mt = self._parse_llamacpp_metrics(
                            self._http_get_text(f"http://127.0.0.1:{port}/metrics", timeout=8)
                        )
                        entry["total_predicted_tokens"] = _mt.get("llamacpp:tokens_predicted_total")
                        entry["total_prompt_tokens"] = _mt.get("llamacpp:prompt_tokens_total")
                    except Exception:
                        pass

                # ── MTP acceptance: probe ONCE per server lifecycle ──
                # /metrics on this llama.cpp build does not expose MTP drafted/
                # accepted counters, so we determine MTP on/off with a single short
                # probe. It fires exactly once when the model server is first
                # discovered, and again only after a restart (detected via PID
                # change). No periodic re-probing — we never disturb a running
                # server again, so the dashboard simply shows MTP on or off.
                _mt_cache = StatsService._MTP_CACHE.get(port)
                if entry.get("source") == "metrics":
                    # 投机类型已由命令行权威判定，速率由 /metrics 被动获取 ——
                    # 无需再发探测请求。繁忙服务上探测必排队超时（曾致接口 20~26s
                    # 且恒误判「MTP 关」），同时也会打扰正在服务的模型。
                    pass
                elif not (_mt_cache and _mt_cache.get("pid") == pid and "mtp" in _mt_cache):
                    try:
                        _pr = self._probe_server(port)
                        _pm = _pr.get("mtp") or {}
                        # 只补接受率明细，enabled 一律以命令行为准
                        if _pm.get("drafted"):
                            entry["mtp"]["acceptance"] = _pm.get("acceptance")
                            entry["mtp"]["drafted"] = _pm.get("drafted")
                            entry["mtp"]["accepted"] = _pm.get("accepted")
                        if not entry.get("tok_s"):
                            entry["tok_s"] = _pr.get("tok_s") or 0.0
                        if not entry.get("prompt_tok_s"):
                            entry["prompt_tok_s"] = _pr.get("prompt_tok_s") or 0.0
                        pk_tok, pk_prompt = StatsService._record_peak(
                            port, _pr.get("tok_s"), _pr.get("prompt_tok_s")
                        )
                        entry["tok_s_peak"] = pk_tok
                        entry["prompt_tok_s_peak"] = pk_prompt
                        StatsService._MTP_CACHE[port] = {
                            "ts": time.time(), "mtp": dict(entry["mtp"]), "pid": pid,
                        }
                    except Exception as _e:
                        print(f"[model-metrics] MTP probe failed port {port}: {_e!r}", flush=True)
                        StatsService._MTP_CACHE[port] = {
                            "ts": time.time(), "mtp": entry["mtp"], "pid": pid,
                        }
                else:
                    _cm = _mt_cache.get("mtp") or {}
                    for _k in ("acceptance", "drafted", "accepted"):
                        if _cm.get(_k) is not None:
                            entry["mtp"][_k] = _cm[_k]

                servers.append(entry)
        except Exception as e:
            print(f"[model-metrics] discovery error: {e}")

        # system-wide GPU + memory (GB10 unified memory: memory may be [N/A])
        gpu = None
        try:
            import subprocess as _sp
            out = _sp.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            ).stdout
            if out:
                parts = [p.strip() for p in out.split(",")]

                def _num(x):
                    x = (x or "").strip()
                    if x == "" or x.upper() == "[N/A]" or x.upper() == "N/A":
                        return None
                    try:
                        return float(x)
                    except ValueError:
                        return None

                if parts:
                    gpu = {
                        "utilization": _num(parts[0]),
                        "memory_used": (_num(parts[1]) * 1024 * 1024) if (len(parts) > 1 and _num(parts[1]) is not None) else None,
                        "memory_total": (_num(parts[2]) * 1024 * 1024) if (len(parts) > 2 and _num(parts[2]) is not None) else None,
                        "temperature_c": _num(parts[3]) if len(parts) > 3 else None,
                    }
        except Exception:
            gpu = None

        vmem = psutil.virtual_memory()

        return {
            "data": {
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                "discovered_count": len(servers),
                "gpu": gpu,
                "system_memory": {
                    "used": vmem.used,
                    "total": vmem.total,
                    "percent": vmem.percent,
                },
                "servers": servers,
            }
        }


    def _ensure_disk_io_columns(self, conn):
        """Add disk_io columns if they don't exist (DB migration)."""
        try:
            conn.execute("ALTER TABLE system_metrics ADD COLUMN disk_io_read_bytes INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE system_metrics ADD COLUMN disk_io_write_bytes INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE system_metrics ADD COLUMN disk_io_read_rate REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE system_metrics ADD COLUMN disk_io_write_rate REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists

    # ── Internal helpers ────────────────────────────────

    def _summary_stats(self) -> Dict[str, Any]:
        """Aggregate summary stats from DB."""
        conn = self.db.get_connection()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM request_stats")
            total = cur.fetchone()[0]

            cur2 = conn.execute(
                "SELECT AVG(response_time) FROM request_stats"
            )
            avg_rt = cur2.fetchone()[0] or 0

            return {
                "totalRequests": total,
                "avgResponseTime": round(avg_rt, 2),
            }
        finally:
            conn.close()

    # ── Table creation ──────────────────────────────────

    def create_tables(self):
        """Create all stats tables if they don't exist."""
        conn = self.db.get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cpu_usage REAL,
                    memory_total INTEGER,
                    memory_used INTEGER,
                    memory_percent REAL,
                    disk_total INTEGER,
                    disk_used INTEGER,
                    disk_percent REAL,
                    network_bytes_sent INTEGER,
                    network_bytes_recv INTEGER,
                    gpu_utilization REAL,
                    gpu_memory_used REAL,
                    gpu_memory_total REAL,
                    gpu_temperature REAL DEFAULT NULL,
                    disk_io_read_bytes INTEGER DEFAULT 0,
                    disk_io_write_bytes INTEGER DEFAULT 0,
                    disk_io_read_rate REAL DEFAULT 0,
                    disk_io_write_rate REAL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS request_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    response_time REAL NOT NULL,
                    client_ip TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_key_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id INTEGER NOT NULL,
                    request_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (key_id) REFERENCES api_keys(id),
                    FOREIGN KEY (request_id) REFERENCES request_stats(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id INTEGER,
                    request_id INTEGER,
                    model_family TEXT,
                    model_name TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (key_id) REFERENCES api_keys(id),
                    FOREIGN KEY (request_id) REFERENCES request_stats(id)
                )
            """)
            conn.commit()
        finally:
            conn.close()
