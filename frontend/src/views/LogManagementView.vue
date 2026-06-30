<template>
  <div class="log-mgmt-view">
    <div class="log-header">
      <h2>{{ t("logs.title") }}</h2>
      <div class="header-actions">
        <button @click="loadSummary" class="btn-secondary">{{ t("logs.refresh") }}</button>
      </div>
    </div>

    <!-- 日志摘要 -->
    <div class="summary-cards">
      <div class="card" v-for="day in logSummary" :key="day.date">
        <div class="card-date">{{ day.date }}</div>
        <div class="card-stats">
          <div class="stat">
            <span class="stat-num">{{ day.total }}</span>
            <span class="stat-label">{{ t("logs.total") }}</span>
          </div>
          <div class="stat">
            <span class="stat-num error">{{ day.errors }}</span>
            <span class="stat-label">{{ t("logs.errors") }}</span>
          </div>
          <div class="stat">
            <span class="stat-num warn">{{ day.warnings }}</span>
            <span class="stat-label">{{ t("logs.warnings") }}</span>
          </div>
        </div>
        <div class="card-actions">
          <button @click="queryDay(day.date)" class="btn-small">{{ t("logs.view") }}</button>
          <button @click="archiveDay(day.date)" class="btn-small btn-archive">{{ t("logs.archive") }}</button>
          <button @click="deleteDay(day.date)" class="btn-small btn-delete">{{ t("logs.delete") }}</button>
        </div>
      </div>
      <div v-if="logSummary.length === 0" class="empty-state">
        {{ t("logs.noData") }}
      </div>
    </div>

    <!-- 清理操作 -->
    <div class="cleanup-section">
      <h3>{{ t("logs.cleanup") }}</h3>
      <div class="cleanup-form">
        <div class="form-row">
          <label>{{ t("logs.retentionDays") }}</label>
          <input v-model.number="retentionDays" type="number" min="1" max="365" class="input-number" />
          <button @click="cleanupLogs" class="btn-warning">{{ t("logs.cleanupBtn") }}</button>
        </div>
        <p class="hint">{{ t("logs.cleanupHint") }}</p>
      </div>
    </div>

    <!-- 日志查询 -->
    <div class="query-section">
      <h3>{{ t("logs.query") }}</h3>
      <div class="query-form">
        <div class="form-row">
          <input v-model="queryDate" type="date" class="input-text" />
          <select v-model="queryLevel" class="input-select">
            <option value="">{{ t("logs.allLevels") }}</option>
            <option value="INFO">{{ t("logs.info") }}</option>
            <option value="WARNING">{{ t("logs.warning") }}</option>
            <option value="ERROR">{{ t("logs.error") }}</option>
          </select>
          <input v-model="queryKeyword" :placeholder="t('logs.keyword')" class="input-text" />
          <button @click="queryLogs" class="btn-primary">{{ t("logs.search") }}</button>
        </div>
      </div>
      <div class="query-results" v-if="queryResults.length > 0">
        <div class="result-count">{{ t("logs.found", { count: queryResults.length }) }}</div>
        <div class="results-list">
          <div v-for="(log, idx) in queryResults" :key="idx" class="log-entry" :class="'level-' + log.level">
            <span class="log-time">{{ log.timestamp }}</span>
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
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const logSummary = ref<any[]>([]);
const retentionDays = ref(30);
const queryDate = ref("");
const queryLevel = ref("");
const queryKeyword = ref("");
const queryResults = ref<any[]>([]);

async function loadSummary() {
  try {
    const res = await fetch("/api/logs/summary?days=30", { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      logSummary.value = (data.days || [])
        .filter((d: any) => d.total > 0)
        .sort((a: any, b: any) => (b.date > a.date ? 1 : -1));
    }
  } catch (e) {
    console.error("Failed to load summary:", e);
  }
}

async function queryDay(date: string) {
  queryDate.value = date;
  await queryLogs();
}

async function queryLogs() {
  try {
    const body: any = {
      date_from: queryDate.value,
      date_to: queryDate.value,
      limit: 200,
    };
    if (queryLevel.value) body.level = queryLevel.value;
    if (queryKeyword.value) body.keyword = queryKeyword.value;

    const res = await fetch("/api/logs/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    });
    if (res.ok) {
      const data = await res.json();
      queryResults.value = data.entries || [];
    }
  } catch (e) {
    console.error("Failed to query logs:", e);
  }
}

async function archiveDay(date: string) {
  if (!confirm(t("logs.confirmArchive", { date }))) return;
  try {
    const res = await fetch("/api/logs/archive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: date }),
      credentials: "include",
    });
    if (res.ok) loadSummary();
  } catch (e) {
    console.error("Failed to archive:", e);
  }
}

async function deleteDay(date: string) {
  if (!confirm(t("logs.confirmDelete", { date }))) return;
  try {
    const res = await fetch("/api/logs/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: date }),
      credentials: "include",
    });
    if (res.ok) loadSummary();
  } catch (e) {
    console.error("Failed to delete:", e);
  }
}

async function cleanupLogs() {
  if (!confirm(t("logs.confirmCleanup", { days: retentionDays.value }))) return;
  try {
    const res = await fetch("/api/logs/cleanup", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days: retentionDays.value }),
    });
    if (res.ok) loadSummary();
  } catch (e) {
    console.error("Failed to cleanup:", e);
  }
}

onMounted(loadSummary);
</script>

<style scoped>
.log-mgmt-view {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.log-header h2 {
  margin: 0;
  font-size: 1.5em;
  color: #e0e0ff;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.card {
  background: #1a1a2e;
  border: 1px solid #2d2d4a;
  border-radius: 10px;
  padding: 16px;
}

.card-date {
  font-size: 1.1em;
  font-weight: 700;
  color: #e0e0ff;
  margin-bottom: 12px;
}

.card-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-num {
  font-size: 1.4em;
  font-weight: 700;
  color: #e0e0ff;
}

.stat-num.error { color: #f87171; }
.stat-num.warn { color: #fbbf24; }

.stat-label {
  font-size: 0.75em;
  color: #888;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.btn-small {
  padding: 4px 12px;
  border: 1px solid #2d2d4a;
  border-radius: 4px;
  background: #0f0f1a;
  color: #e0e0ff;
  cursor: pointer;
  font-size: 0.82em;
}

.btn-small:hover { background: #2d2d4a; }
.btn-archive { border-color: #60a5fa; color: #60a5fa; }
.btn-delete { border-color: #f87171; color: #f87171; }

.cleanup-section,
.query-section {
  background: #1a1a2e;
  border: 1px solid #2d2d4a;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 24px;
}

.cleanup-section h3,
.query-section h3 {
  margin: 0 0 16px 0;
  font-size: 1em;
  color: #e0e0ff;
}

.form-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.input-text,
.input-select,
.input-number {
  padding: 8px 12px;
  background: #0f0f1a;
  color: #e0e0ff;
  border: 1px solid #2d2d4a;
  border-radius: 6px;
  font-size: 0.9em;
}

.btn-primary {
  padding: 8px 20px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.btn-primary:hover { background: #6b5cc4; }

.btn-warning {
  padding: 8px 20px;
  background: #5a3a1a;
  color: #fbbf24;
  border: 1px solid #fbbf24;
  border-radius: 6px;
  cursor: pointer;
}

.btn-warning:hover { background: #7a4a2a; }

.hint {
  font-size: 0.82em;
  color: #888;
  margin-top: 8px;
}

.query-results {
  margin-top: 16px;
}

.result-count {
  font-size: 0.85em;
  color: #888;
  margin-bottom: 8px;
}

.results-list {
  max-height: 400px;
  overflow-y: auto;
  font-family: 'Fira Code', monospace;
  font-size: 0.8em;
}

.log-entry {
  display: flex;
  gap: 12px;
  padding: 6px 10px;
  border-bottom: 1px solid #1a1a2e;
  align-items: center;
}

.log-entry:hover { background: #1a1a2e; }

.log-time { color: #666; flex-shrink: 0; }
.log-level { flex-shrink: 0; font-weight: 600; min-width: 60px; }
.log-module { color: #818cf8; flex-shrink: 0; min-width: 80px; }

.level-INFO { color: #60a5fa; }
.level-WARNING { color: #fbbf24; }
.level-ERROR { color: #f87171; }

.log-message {
  color: #c0c0e0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-state {
  text-align: center;
  color: #666;
  padding: 40px;
  border: 2px dashed #2d2d4a;
  border-radius: 8px;
}
</style>
