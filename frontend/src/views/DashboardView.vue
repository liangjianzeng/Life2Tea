<template>
  <div class="dashboard-view">
    <!-- 页面标题 -->
    <div class="dashboard-header">
      <h2>{{ t("dashboard.title") }}</h2>
      <div class="header-actions">
        <span class="refresh-hint">{{ t("dashboard.autoRefresh") }}</span>
        <button class="refresh-btn" @click="refreshAll" :disabled="loading">
          {{ loading ? t("dashboard.refreshing") : t("dashboard.refresh") }}
        </button>
      </div>
    </div>

    <!-- 系统概览卡片 -->
    <div class="overview-cards">
      <div class="card">
        <div class="card-icon cpu-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="4" y="4" width="16" height="16" rx="2" />
            <rect x="9" y="9" width="6" height="6" />
            <line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" />
            <line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" />
            <line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="15" x2="4" y2="15" />
            <line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="15" x2="23" y2="15" />
          </svg>
        </div>
        <div class="card-info">
          <div class="card-value">{{ metrics.cpu }}%</div>
          <div class="card-label">{{ t("dashboard.cpuUsage") }}</div>
        </div>
        <div class="card-trend" :class="metrics.cpu > 80 ? 'trend-up' : 'trend-ok'">
          {{ metrics.cpu > 80 ? '⚠' : '●' }}
        </div>
      </div>

      <div class="card">
        <div class="card-icon mem-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="7" width="20" height="10" rx="2" />
            <line x1="6" y1="11" x2="6" y2="13" /><line x1="10" y1="11" x2="10" y2="13" />
            <line x1="14" y1="11" x2="14" y2="13" /><line x1="18" y1="11" x2="18" y2="13" />
          </svg>
        </div>
        <div class="card-info">
          <div class="card-value">{{ formatMemory(metrics.memory.used, metrics.memory.total) }}</div>
          <div class="card-label">{{ t("dashboard.memoryUsage") }}</div>
        </div>
        <div class="card-progress">
          <div class="progress-bar" :style="{ width: memoryPercent + '%' }"
               :class="memoryPercent > 80 ? 'bar-warning' : memoryPercent > 60 ? 'bar-ok' : 'bar-good'"></div>
        </div>
      </div>

      <div class="card" v-if="metrics.gpu">
        <div class="card-icon gpu-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="6" width="20" height="12" rx="2" />
            <line x1="6" y1="10" x2="6" y2="14" /><line x1="10" y1="10" x2="10" y2="14" />
            <line x1="14" y1="10" x2="14" y2="14" /><line x1="18" y1="10" x2="18" y2="14" />
          </svg>
        </div>
        <div class="card-info">
          <div class="card-value">{{ metrics.gpu.utilization }}%</div>
          <div class="card-label">{{ t("dashboard.gpuUsage") }}</div>
        </div>
        <div class="card-progress">
          <div class="progress-bar" :style="{ width: gpuMemoryPercent + '%' }"
               :class="gpuMemoryPercent > 80 ? 'bar-warning' : gpuMemoryPercent > 60 ? 'bar-ok' : 'bar-good'"></div>
        </div>
        <div class="card-sub">
          {{ formatGpuMemory(metrics.gpu.memory_used, metrics.gpu.memory_total) }} {{ t("dashboard.gpuMemory") }}
        </div>
      </div>

      <div class="card">
        <div class="card-icon req-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="22,12 18,12 15,21 9,3 6,12 2,12" />
          </svg>
        </div>
        <div class="card-info">
          <div class="card-value">{{ stats.totalRequests }}</div>
          <div class="card-label">{{ t("dashboard.totalRequests") }}</div>
        </div>
        <div class="card-sub">{{ stats.avgResponseTime }}ms {{ t("dashboard.avgLatency") }}</div>
      </div>

      <div class="card">
        <div class="card-icon net-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="12" x2="16" y2="16" />
          </svg>
        </div>
        <div class="card-info">
          <div class="card-value">{{ formatNetwork(metrics.network.bytes_sent) }}</div>
          <div class="card-label">{{ t("dashboard.netOutbound") }}</div>
        </div>
        <div class="card-sub">{{ formatNetwork(metrics.network.bytes_recv) }} {{ t("dashboard.netInbound") }}</div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="charts-grid">
      <div class="chart-panel">
        <div class="chart-header">
          <h3>{{ t("dashboard.resourceHistory") }}</h3>
          <div class="chart-tabs">
            <button v-for="tab in resourceTabs" :key="tab"
                    :class="['tab-btn', { active: activeResourceTab === tab }]"
                    @click="activeResourceTab = tab">
              {{ tab === '1h' ? t("dashboard.lastHour") : tab === '6h' ? t("dashboard.last6Hours") : t("dashboard.last24Hours") }}
            </button>
          </div>
        </div>
        <div class="chart-body">
          <LineChart :data="resourceHistory" :unit="activeResourceTab === '1h' ? '%' : 'MB'" :maxValue="activeResourceTab === '1h' ? 100 : undefined" />
        </div>
      </div>

      <!-- GPU History Chart -->
      <div class="chart-panel" v-if="hasGpuHistory">
        <div class="chart-header">
          <h3>{{ t("dashboard.gpuHistory") }}</h3>
          <div class="chart-tabs">
            <button v-for="tab in resourceTabs" :key="tab"
                    :class="['tab-btn', { active: activeResourceTab === tab }]"
                    @click="activeResourceTab = tab">
              {{ tab === '1h' ? t("dashboard.lastHour") : tab === '6h' ? t("dashboard.last6Hours") : t("dashboard.last24Hours") }}
            </button>
          </div>
        </div>
        <div class="chart-body">
          <LineChart :data="gpuHistoryData" :unit="'%'" :maxValue="100" />
        </div>
      </div>

      <div class="chart-panel">
        <div class="chart-header">
          <h3>{{ t("dashboard.latencyDistribution") }}</h3>
        </div>
        <div class="chart-body">
          <div class="percentiles">
            <div class="p-item" v-for="p in perfMetrics" :key="p.label">
              <span class="p-label">{{ p.label }}</span>
              <span class="p-value">{{ p.value }}ms</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- API Key 统计 -->
    <div class="chart-panel" v-if="apiKeys.length > 0">
      <div class="chart-header">
        <h3>{{ t("dashboard.apiKeyStats") }}</h3>
        <button class="view-all-link" @click="$router.push('/api-keys')">{{ t("dashboard.viewAll") }}</button>
      </div>
      <div class="chart-body">
        <div class="api-keys-grid">
          <div class="api-key-card" v-for="key in apiKeys" :key="key.name">
            <div class="key-name">{{ key.name }}</div>
            <div class="key-stats">
              <div class="stat-row">
                <span>{{ t("dashboard.requestCount") }}</span>
                <span class="stat-value">{{ key.request_count }}</span>
              </div>
              <div class="stat-row">
                <span>{{ t("dashboard.tokenCount") }}</span>
                <span class="stat-value">{{ key.token_count?.toLocaleString() || '-' }}</span>
              </div>
              <div class="stat-row">
                <span>{{ t("dashboard.avgResponseTime") }}</span>
                <span class="stat-value">{{ key.avg_response_time?.toFixed(1) || '-' }}ms</span>
              </div>
              <div class="stat-row">
                <span>{{ t("dashboard.lastUsed") }}</span>
                <span class="stat-value time">{{ formatTime(key.last_used_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Token 统计 & 模型指标 -->
    <div class="info-cards">
      <div class="info-card">
        <div class="info-icon token-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 6h16M4 12h16M4 18h10" />
          </svg>
        </div>
        <div class="info-content">
          <h4>{{ t("dashboard.tokenStats") }}</h4>
          <p class="coming-soon">{{ t("dashboard.comingSoon") }}</p>
          <p class="info-desc">{{ t("dashboard.tokenDesc") }}</p>
        </div>
      </div>

      <div class="info-card">
        <div class="info-icon model-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <circle cx="9" cy="9" r="2" /><circle cx="15" cy="9" r="2" />
            <path d="M9 15l6 6M15 15l-6 6" />
          </svg>
        </div>
        <div class="info-content">
          <h4>{{ t("dashboard.modelMetrics") }}</h4>
          <p class="coming-soon">{{ t("dashboard.comingSoon") }}</p>
          <p class="info-desc">{{ t("dashboard.modelDesc") }}</p>
        </div>
      </div>
    </div>

    <!-- 系统日志 -->
    <div class="chart-panel">
      <div class="chart-header">
        <h3>{{ t("dashboard.recentLogs") }}</h3>
        <LogViewer :logs="recentLogs" />
      </div>
      <div class="chart-body logs-body">
        <div v-if="recentLogs.length === 0" class="empty-logs">{{ t("dashboard.noLogs") }}</div>
        <div v-else class="logs-list">
          <div v-for="(log, idx) in recentLogs" :key="idx" class="log-entry" :class="'level-' + log.level">
            <span class="log-time">{{ formatTime(log.timestamp) }}</span>
            <span class="log-level" :class="'level-' + log.level">{{ log.level }}</span>
            <span class="log-module">{{ log.module }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import { getStatsDashboard, getSystemMetrics, getApiKeyStats, getPerformanceMetrics, getResourceUsage, getRecentLogs } from "../services/stats";
import LineChart from "../components/LineChart.vue";
import LogViewer from "../components/LogViewer.vue";

const { t } = useI18n();

// ── Data ──
const metrics = ref<any>({
  cpu: 0,
  memory: { used: 0, total: 0 },
  disk: { used: 0, total: 0 },
  network: { bytes_sent: 0, bytes_recv: 0 },
  gpu: null,
});

const stats = ref<any>({
  totalRequests: 0,
  avgResponseTime: 0,
  errorRate: 0,
});

const resourceHistory = ref<any[]>([]);
const perfMetrics = ref<any[]>([]);
const apiKeys = ref<any[]>([]);
const recentLogs = ref<any[]>([]);

const loading = ref(false);
const activeResourceTab = ref("1h");

const resourceTabs = computed(() => ["1h", "6h", "24h"]);

// ── Computed ──
const memoryPercent = computed(() => {
  if (!metrics.value.memory.total) return 0;
  return Math.round((metrics.value.memory.used / metrics.value.memory.total) * 100);
});

const gpuMemoryPercent = computed(() => {
  if (!metrics.value.gpu || !metrics.value.gpu.memory_total) return 0;
  return Math.round((metrics.value.gpu.memory_used / metrics.value.gpu.memory_total) * 100);
});

const hasGpuHistory = computed(() => {
  return resourceHistory.value.some((d: any) => d.gpu != null);
});

const gpuHistoryData = computed(() => {
  return resourceHistory.value
    .filter((d: any) => d.gpu != null)
    .map((d: any) => ({
      timestamp: d.timestamp,
      gpu: d.gpu.utilization,
    }));
});

// ── Format helpers ──
function formatMemory(used: number, total: number): string {
  if (!total) return "-";
  return `${(used / 1024 / 1024 / 1024).toFixed(1)} / ${(total / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function formatGpuMemory(used: number, total: number): string {
  if (!total) return "-";
  // nvidia-smi returns MB
  return `${(used / 1024).toFixed(1)} / ${(total / 1024).toFixed(1)} GB`;
}

function formatNetwork(bytes: number): string {
  if (!bytes) return "0 B";
  if (bytes > 1024 * 1024 * 1024) return (bytes / 1024 / 1024 / 1024).toFixed(1) + " GB";
  if (bytes > 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
  if (bytes > 1024) return (bytes / 1024).toFixed(1) + " KB";
  return bytes + " B";
}

function formatTime(ts: string | null): string {
  if (!ts) return "-";
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString();
  } catch {
    return ts;
  }
}

// ── Fetch functions ──
async function refreshDashboard() {
  try {
    const [dash, keys, perf] = await Promise.all([
      getStatsDashboard(),
      getApiKeyStats(),
      getPerformanceMetrics(),
    ]);

    stats.value = dash.stats || {};
    apiKeys.value = keys.data?.slice(0, 6) || [];
    perfMetrics.value = perf.data || [];
  } catch (e) {
    console.error("Failed to refresh dashboard:", e);
  }
}

async function refreshMetrics() {
  try {
    const [sys, res, logs] = await Promise.all([
      getSystemMetrics(),
      getResourceUsage(activeResourceTab.value),
      getRecentLogs(),
    ]);

    metrics.value = sys || {};
    resourceHistory.value = res.data || [];
    recentLogs.value = (logs.data || []).slice(0, 20);
  } catch (e) {
    console.error("Failed to refresh metrics:", e);
  }
}

async function refreshAll() {
  loading.value = true;
  try {
    await Promise.all([refreshDashboard(), refreshMetrics()]);
  } finally {
    loading.value = false;
  }
}

// ── Lifecycle ──
let refreshTimer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  refreshAll();
  refreshTimer = setInterval(refreshAll, 10000); // Refresh every 10s
});

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<style scoped>
.dashboard-view {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.dashboard-header h2 {
  margin: 0;
  font-size: 1.5em;
  color: #e0e0ff;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.refresh-hint {
  font-size: 0.8em;
  color: #666;
}

.refresh-btn {
  padding: 6px 16px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85em;
}

.refresh-btn:hover:not(:disabled) {
  background: #3d3d5a;
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Overview cards */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.card {
  background: #1a1a2e;
  border: 1px solid #2d2d4a;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: border-color 0.2s;
}

.card:hover {
  border-color: #534ab7;
}

.card-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cpu-icon { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
.mem-icon { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.gpu-icon { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
.req-icon { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.net-icon { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }

.card-info {
  flex: 1;
}

.card-value {
  font-size: 1.4em;
  font-weight: 700;
  color: #e0e0ff;
}

.card-label {
  font-size: 0.8em;
  color: #888;
  margin-top: 2px;
}

.card-sub {
  font-size: 0.75em;
  color: #666;
  margin-top: 4px;
}

.card-trend {
  font-size: 1.2em;
}

.trend-up { color: #f87171; }
.trend-ok { color: #34d399; }

.card-progress {
  width: 60px;
  height: 6px;
  background: #2d2d4a;
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}

.bar-good { background: #10b981; }
.bar-ok { background: #f59e0b; }
.bar-warning { background: #ef4444; }

/* Charts grid */
.charts-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}

.chart-panel {
  background: #1a1a2e;
  border: 1px solid #2d2d4a;
  border-radius: 12px;
  overflow: hidden;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #2d2d4a;
}

.chart-header h3 {
  margin: 0;
  font-size: 1em;
  color: #e0e0ff;
}

.chart-tabs {
  display: flex;
  gap: 4px;
}

.tab-btn {
  padding: 4px 10px;
  background: transparent;
  color: #888;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8em;
}

.tab-btn.active {
  background: #2d2d4a;
  color: #e0e0ff;
  border-color: #534ab7;
}

.chart-body {
  padding: 16px 20px;
}

.view-all-link {
  color: #818cf8;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.85em;
}

.view-all-link:hover {
  text-decoration: underline;
}

/* Percentiles */
.percentiles {
  display: grid;
  gap: 8px;
}

.p-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: #0f0f1a;
  border-radius: 6px;
}

.p-label {
  color: #888;
  font-size: 0.9em;
}

.p-value {
  color: #e0e0ff;
  font-weight: 600;
}

/* API keys */
.api-keys-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.api-key-card {
  background: #0f0f1a;
  border: 1px solid #2d2d4a;
  border-radius: 8px;
  padding: 16px;
}

.key-name {
  font-weight: 600;
  color: #e0e0ff;
  margin-bottom: 12px;
  font-size: 0.95em;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 0.85em;
}

.stat-row span:first-child {
  color: #888;
}

.stat-value {
  color: #e0e0ff;
  font-weight: 500;
}

.stat-value.time {
  color: #888;
  font-size: 0.85em;
}

/* Info cards (token, model) */
.info-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}

.info-card {
  background: #1a1a2e;
  border: 1px dashed #2d2d4a;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  gap: 16px;
  align-items: center;
}

.info-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.token-icon { background: rgba(168, 85, 247, 0.15); color: #c084fc; }
.model-icon { background: rgba(236, 72, 153, 0.15); color: #f472b6; }

.info-content h4 {
  margin: 0 0 4px 0;
  color: #e0e0ff;
  font-size: 0.95em;
}

.coming-soon {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(129, 140, 248, 0.15);
  color: #818cf8;
  border-radius: 4px;
  font-size: 0.75em;
  font-weight: 600;
  margin-bottom: 4px;
}

.info-desc {
  font-size: 0.82em;
  color: #666;
  margin: 0;
}

/* Logs */
.logs-body {
  max-height: 400px;
  overflow-y: auto;
  padding: 0;
}

.empty-logs {
  text-align: center;
  color: #666;
  padding: 40px;
  font-size: 0.9em;
}

.log-entry {
  display: flex;
  gap: 12px;
  padding: 8px 20px;
  font-family: 'Fira Code', monospace;
  font-size: 0.8em;
  border-bottom: 1px solid #1a1a2e;
  align-items: center;
}

.log-entry:hover {
  background: #1a1a2e;
}

.log-time { color: #666; flex-shrink: 0; }
.log-module { color: #818cf8; flex-shrink: 0; min-width: 80px; }

.log-level {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.85em;
  font-weight: 600;
  flex-shrink: 0;
}

.level-INFO { color: #60a5fa; background: rgba(96, 165, 250, 0.1); }
.level-WARNING { color: #fbbf24; background: rgba(251, 191, 36, 0.1); }
.level-ERROR { color: #f87171; background: rgba(248, 113, 113, 0.1); }
.level-DEBUG { color: #888; }

.log-message {
  color: #c0c0e0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }

  .overview-cards {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
