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

from .database import Database


class StatsService:
    """System statistics service"""

    def __init__(self, db: Database):
        self.db = db

    # ── Collectors ──────────────────────────────────────

    def __init__(self, db: Database):
        self.db = db
        self._last_disk_io = None  # for computing disk IO rate

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
            },
            "timestamp": now.isoformat(),
            "gpu": None,
        }

        # NVIDIA GPU monitoring
        try:
            result = subprocess.run(
                ['nvidia-smi',
                 '--query-gpu=utilization.gpu,memory.used,memory.total',
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

                metrics["gpu"] = {
                    "utilization": safe_float(parts[0]),
                    "memory_used": safe_float(parts[1]),
                    "memory_total": safe_float(parts[2]),
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
                 gpu_utilization, gpu_memory_used, gpu_memory_total)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                              gpu_utilization, gpu_memory_used, gpu_memory_total,
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
                        }
                    result.append({
                        "timestamp": r[0],
                        "cpu": r[1],
                        "memory": {"used": r[2], "total": r[3]},
                        "gpu": gpu,
                        "disk_io": {
                            "read_rate": r[7] or 0,
                            "write_rate": r[8] or 0,
                        },
                    })
            else:
                cur = conn.execute(
                    """SELECT timestamp, cpu_usage, memory_used, memory_total,
                              gpu_utilization, gpu_memory_used, gpu_memory_total
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

    def get_model_metrics(self) -> Dict[str, Any]:
        """Get model running metrics."""
        conn = self.db.get_connection()
        try:
            # Query system metrics for GPU/CPU utilization
            query = """
                SELECT timestamp, gpu_utilization, gpu_memory_used, gpu_memory_total,
                       cpu_usage, memory_percent
                FROM system_metrics
                ORDER BY timestamp DESC
                LIMIT 100
            """
            cursor = conn.execute(query)
            rows = cursor.fetchall()

            metrics = []
            for row in rows:
                metrics.append({
                    "timestamp": row[0],
                    "gpu_utilization": row[1],
                    "gpu_memory_used": row[2],
                    "gpu_memory_total": row[3],
                    "cpu_usage": row[4],
                    "memory_percent": row[5],
                })

            return {"data": metrics}
        except Exception as e:
            print(f"Error getting model metrics: {e}")
            return {"data": []}
        finally:
            conn.close()

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
