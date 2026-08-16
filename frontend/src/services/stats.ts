/**
 * stats.ts — Statistics and monitoring service for the frontend.
 *
 * Provides functions to fetch system metrics, resource usage,
 * performance metrics, API key stats, and logs.
 */

const API_BASE = "/api";

/**
 * Fetch dashboard statistics (summary data).
 */
export async function getStatsDashboard() {
  const res = await fetch(`${API_BASE}/stats/dashboard`, { credentials: "include" });
  if (!res.ok) throw new Error(`Stats dashboard: ${res.status}`);
  return res.json();
}

/**
 * Fetch current system metrics (CPU, memory, disk, network, GPU).
 */
export async function getSystemMetrics() {
  const res = await fetch(`${API_BASE}/stats/system`, { credentials: "include" });
  if (!res.ok) throw new Error(`System metrics: ${res.status}`);
  return res.json();
}

/**
 * Fetch resource usage history over time.
 * @param range - Time range: "1h", "6h", "24h"
 */
export async function getResourceUsage(range: string = "1h") {
  const res = await fetch(`${API_BASE}/stats/resources?range=${range}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Resource usage: ${res.status}`);
  return res.json();
}

/**
 * Fetch performance metrics (P50/P95/P99 latency).
 */
export async function getPerformanceMetrics() {
  const res = await fetch(`${API_BASE}/stats/performance`, { credentials: "include" });
  if (!res.ok) throw new Error(`Performance: ${res.status}`);
  return res.json();
}

/**
 * Fetch token usage statistics.
 */
export async function getTokenUsage() {
  const res = await fetch(`${API_BASE}/stats/token-usage`, { credentials: "include" });
  if (!res.ok) throw new Error(`Token usage: ${res.status}`);
  return res.json();
}

/**
 * Fetch API key usage statistics.
 */
export async function getApiKeyStats() {
  const res = await fetch(`${API_BASE}/stats/api-keys`, { credentials: "include" });
  if (!res.ok) throw new Error(`API keys: ${res.status}`);
  return res.json();
}

/**
 * Fetch recent request statistics.
 */
export async function getRequestStats() {
  const res = await fetch(`${API_BASE}/stats/requests`, { credentials: "include" });
  if (!res.ok) throw new Error(`Requests: ${res.status}`);
  return res.json();
}

/**
 * Fetch system logs with optional filtering.
 */
export async function getRecentLogs(limit: number = 50, level?: string) {
  let url = `${API_BASE}/stats/recent-logs?limit=${limit}`;
  if (level) url += `&level=${level}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`Logs: ${res.status}`);
  return res.json();
}


/**
 * Fetch live model server metrics (discovered llama.cpp processes).
 */
export async function getModelMetrics() {
  const res = await fetch(`${API_BASE}/stats/model-metrics`, { credentials: "include" });
  if (!res.ok) throw new Error(`Model metrics: ${res.status}`);
  return res.json();
}

/**
 * Fetch per-model usage summary (requests / tokens / tps) for a period.
 * @param period - "day", "week", "month", "all"
 */
export async function getGatewaySummary(period: string = "month") {
  const res = await fetch(`${API_BASE}/stats/gateway/summary?period=${period}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Gateway summary: ${res.status}`);
  return res.json();
}
