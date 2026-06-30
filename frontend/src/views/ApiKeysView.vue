<template>
  <div class="api-keys-view">
    <h2>{{ t("settings.apiKeys.title") }}</h2>

    <div class="api-keys-create">
      <h3>{{ t("settings.apiKeys.create") }}</h3>
      <div class="form-row">
        <input
          v-model="newKey.name"
          :placeholder="t('settings.apiKeys.name')"
          class="input-text"
        />
        <select v-model="newKey.scopes" class="input-select">
          <option value="read">{{ t("settings.apiKeys.scopes.read") }}</option>
          <option value="write">{{ t("settings.apiKeys.scopes.write") }}</option>
          <option value="models:read">{{ t("settings.apiKeys.scopes.models.read") }}</option>
          <option value="models:write">{{ t("settings.apiKeys.scopes.models.write") }}</option>
          <option value="chat:infer">{{ t("settings.apiKeys.scopes.chat.infer") }}</option>
          <option value="admin">{{ t("settings.apiKeys.scopes.admin") }}</option>
        </select>
        <input
          v-model.number="newKey.expires"
          type="number"
          min="0"
          :placeholder="t('settings.apiKeys.expires')"
          class="input-number"
        />
        <button @click="createKey" class="btn-primary">
          {{ t("settings.apiKeys.create") }}
        </button>
      </div>
    </div>

    <div class="api-keys-list">
      <div class="list-header">
        <h3>{{ t("settings.apiKeys.title") }}</h3>
        <div class="range-selector">
          <label>{{ t("settings.apiKeys.timeRange") }}</label>
          <select v-model="statRange" @change="loadKeyStats" class="input-select-small">
            <option value="today">{{ t("settings.apiKeys.rangeToday") }}</option>
            <option value="7d">{{ t("settings.apiKeys.range7d") }}</option>
            <option value="30d">{{ t("settings.apiKeys.range30d") }}</option>
          </select>
        </div>
      </div>
      <div v-if="keys.length === 0" class="empty-state">
        {{ t("settings.apiKeys.none") }}
      </div>
      <div v-for="key in keys" :key="key.id" class="api-key-item">
        <div class="key-info">
          <div class="key-name">{{ key.name }}</div>
          <div class="key-meta">
            <span>创建: {{ formatDate(key.created_at_iso) }}</span>
            <span v-if="key.expires_at_iso">过期: {{ formatDate(key.expires_at_iso) }}</span>
            <span v-if="key.remaining_days != null">{{ t("settings.apiKeys.remainingDays", { days: key.remaining_days }) }}</span>
            <span v-else>{{ t("settings.apiKeys.neverExpires") }}</span>
          </div>
          <div class="key-scopes">
            <span v-for="scope in key.scopes" :key="scope" class="scope-badge">{{ scope }}</span>
          </div>
          <div class="key-hash" v-if="key.key">
            {{ t("settings.apiKeys.keyHash") }}: <code>{{ key.key.slice(0, 8) }}...{{ key.key.slice(-4) }}</code>
          </div>
          <div class="key-stats" v-if="keyStatMap[key.name]">
            <div class="stat-row">
              <span>{{ t("settings.apiKeys.useCount") }}</span>
              <span>{{ keyStatMap[key.name].request_count }}</span>
            </div>
            <div class="stat-row" v-if="keyStatMap[key.name].avg_response_time">
              <span>{{ t("settings.apiKeys.avgLatency") }}</span>
              <span>{{ keyStatMap[key.name].avg_response_time }}ms</span>
            </div>
            <div class="stat-row" v-if="keyStatMap[key.name].last_used_at">
              <span>{{ t("settings.apiKeys.lastUsed") }}</span>
              <span>{{ formatStatTime(keyStatMap[key.name].last_used_at) }}</span>
            </div>
          </div>
        </div>
        <div class="key-actions">
          <button
            @click="showKeyDetail(key)"
            class="btn-secondary"
            :title="t('settings.apiKeys.viewDetail')"
          >
            {{ t("settings.apiKeys.viewDetail") }}
          </button>
          <button
            v-if="key.key"
            @click="copyKey(key.id)"
            class="btn-secondary"
            :title="t('settings.apiKeys.copyKey')"
          >
            {{ t("settings.apiKeys.copyKey") }}
          </button>
          <button
            @click="revokeKey(key.id)"
            class="btn-warning"
            :title="t('settings.apiKeys.revoke')"
          >
            {{ t("settings.apiKeys.revoke") }}
          </button>
          <button
            @click="deleteKey(key.id)"
            class="btn-danger"
            :title="t('settings.apiKeys.delete')"
          >
            {{ t("settings.apiKeys.delete") }}
          </button>
        </div>
      </div>
    </div>

    <!-- API Key 请求详情弹窗 -->
    <div v-if="showDetailModal" class="modal-overlay" @click.self="closeDetailModal">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>{{ t("settings.apiKeys.detailTitle", { name: detailKey?.name || '' }) }}</h3>
          <button class="modal-close" @click="closeDetailModal">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="detailLoading" class="loading-state">{{ t("settings.apiKeys.loading") }}</div>
          <div v-else-if="detailRequests.length === 0" class="empty-state">{{ t("settings.apiKeys.noRequests") }}</div>
          <div v-else class="detail-table">
            <table>
              <thead>
                <tr>
                  <th>{{ t("settings.apiKeys.colTime") }}</th>
                  <th>{{ t("settings.apiKeys.colMethod") }}</th>
                  <th>{{ t("settings.apiKeys.colPath") }}</th>
                  <th>{{ t("settings.apiKeys.colStatus") }}</th>
                  <th>{{ t("settings.apiKeys.colLatency") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="req in detailRequests" :key="req.timestamp" :class="'status-' + (req.status_code < 400 ? 'ok' : 'err')">
                  <td>{{ formatStatTime(req.timestamp) }}</td>
                  <td><span class="method-badge" :class="req.method">{{ req.method }}</span></td>
                  <td>{{ req.path }}</td>
                  <td>{{ req.status_code }}</td>
                  <td>{{ req.response_time?.toFixed(1) }}ms</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建成功弹窗 -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="closeCreateModal">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ t("settings.apiKeys.keyCreatedTitle") }}</h3>
          <button class="modal-close" @click="closeCreateModal">&times;</button>
        </div>
        <div class="modal-body">
          <p>{{ t("settings.apiKeys.keyCreatedWarning") }}</p>
          <div class="key-display">
            <code>{{ createdKey }}</code>
            <button class="btn-copy-key" @click="copyCreatedKey">
              {{ t("settings.apiKeys.copyKey") }}
            </button>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-primary" @click="closeCreateModal">{{ t("settings.apiKeys.done") }}</button>
        </div>
      </div>
    </div>

    <div v-if="message" class="message" :class="messageType">
      {{ message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

interface ApiKey {
  id: string;
  name: string;
  scopes: string[];
  created_at: number;
  created_at_iso?: string;
  expires_at?: number;
  expires_at_iso?: string;
  remaining_days?: number;
  revoked: boolean;
  key?: string;
}

const keys = ref<ApiKey[]>([]);
const keyStatMap = ref<Record<string, any>>({});
const showDetailModal = ref(false);
const detailKey = ref<ApiKey | null>(null);
const detailRequests = ref<any[]>([]);
const detailLoading = ref(false);
const newKey = ref({
  name: "",
  scopes: [] as string[],
  expires: 0,
});
const message = ref("");
const messageType = ref<"success" | "error">("success");
const showCreateModal = ref(false);
const createdKey = ref("");
const statRange = ref("today");

async function loadKeys() {
  try {
    const res = await fetch("/api/keys", { credentials: "include" });
    if (!res.ok) throw new Error("Failed to load keys");
    const data = await res.json();
    keys.value = data.keys || [];
  } catch (e: any) {
    showMessage(t("settings.apiKeys.errorLoad", { msg: e.message }), "error");
  }
}

async function createKey() {
  if (!newKey.value.name) {
    showMessage(t("settings.apiKeys.errorName"), "error");
    return;
  }
  if (!newKey.value.scopes || (Array.isArray(newKey.value.scopes) && newKey.value.scopes.length === 0)) {
    showMessage(t("settings.apiKeys.errorSelectScope"), "error");
    return;
  }
  try {
    const res = await fetch("/api/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newKey.value.name,
        scopes: [newKey.value.scopes],
        expires_in_days: newKey.value.expires || null,
      }),
      credentials: "include",
    });
    const data = await res.json();
    if (res.ok) {
      if (data.key) {
        createdKey.value = data.key;
        showCreateModal.value = true;
      } else {
        showMessage(t("settings.apiKeys.successCreate"), "success");
      }
      loadKeys();
      newKey.value = { name: "", scopes: [], expires: 0 };
    } else {
      showMessage(t("settings.apiKeys.errorCreate", { msg: data.detail || "Unknown error" }), "error");
    }
  } catch (e: any) {
    showMessage(t("settings.apiKeys.errorCreate", { msg: e.message }), "error");
  }
}

async function deleteKey(keyId: string) {
  if (!confirm(t("settings.apiKeys.confirmDelete", { name: getKeyName(keyId) }))) {
    return;
  }
  try {
    const res = await fetch(`/api/keys/${keyId}`, { method: "DELETE", credentials: "include" });
    if (res.ok) {
      showMessage(t("settings.apiKeys.successDelete"), "success");
      loadKeys();
    } else {
      showMessage(t("settings.apiKeys.errorDelete"), "error");
    }
  } catch (e: any) {
    showMessage(t("settings.apiKeys.errorDelete", { msg: e.message }), "error");
  }
}

async function revokeKey(keyId: string) {
  if (!confirm(t("settings.apiKeys.confirmRevoke", { name: getKeyName(keyId) }))) {
    return;
  }
  try {
    const res = await fetch(`/api/keys/${keyId}/revoke`, { method: "POST", credentials: "include" });
    if (res.ok) {
      showMessage(t("settings.apiKeys.successRevoke"), "success");
      loadKeys();
    } else {
      showMessage(t("settings.apiKeys.errorRevoke"), "error");
    }
  } catch (e: any) {
    showMessage(t("settings.apiKeys.errorRevoke", { msg: e.message }), "error");
  }
}

function copyKey(keyId: string) {
  const key = keys.value.find((k) => k.id === keyId);
  if (key?.key) {
    navigator.clipboard.writeText(key.key);
    showMessage(t("settings.apiKeys.copied"), "success");
  }
}

function copyCreatedKey() {
  if (createdKey.value) {
    navigator.clipboard.writeText(createdKey.value);
    showMessage(t("settings.apiKeys.copied"), "success");
  }
}

function closeCreateModal() {
  showCreateModal.value = false;
  createdKey.value = "";
}

function getKeyName(keyId: string): string {
  return keys.value.find((k) => k.id === keyId)?.name || keyId;
}

function formatDate(iso: string | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("zh-CN");
}

function showMessage(text: string, type: "success" | "error") {
  message.value = text;
  messageType.value = type;
  setTimeout(() => {
    message.value = "";
  }, 5000);
}

async function loadKeyStats() {
  try {
    const res = await fetch(`/api/stats/api-keys?range=${statRange.value}`, { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      const map: Record<string, any> = {};
      for (const k of data.data || []) {
        map[k.name] = k;
      }
      keyStatMap.value = map;
    }
  } catch (e) {
    console.error("Failed to load key stats:", e);
  }
}

async function showKeyDetail(key: ApiKey) {
  detailKey.value = key;
  showDetailModal.value = true;
  detailLoading.value = true;
  detailRequests.value = [];
  try {
    const res = await fetch(`/api/stats/key-detail?key_id=${encodeURIComponent(key.id)}&limit=100`, { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      detailRequests.value = data.data || [];
    }
  } catch (e) {
    console.error("Failed to load key detail:", e);
  } finally {
    detailLoading.value = false;
  }
}

function closeDetailModal() {
  showDetailModal.value = false;
  detailKey.value = null;
  detailRequests.value = [];
}

function formatStatTime(ts: string): string {
  if (!ts) return "-";
  try { return new Date(ts).toLocaleString("zh-CN"); } catch { return ts; }
}

onMounted(async () => {
  await loadKeys();
  await loadKeyStats();
});
</script>

<style scoped>
.api-keys-view {
  max-width: 900px;
  margin: 0 auto;
  padding: 16px;
  height: 100%;
  overflow-y: auto;
}

h2 {
  margin: 0 0 24px 0;
  padding-bottom: 12px;
  border-bottom: 1px solid #2d2d4a;
}

h3 {
  margin: 24px 0 12px 0;
  font-size: 1em;
  opacity: 0.8;
}

.api-keys-create {
  margin-bottom: 24px;
}

.form-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.input-text,
.input-select,
.input-number {
  flex: 1;
  min-width: 150px;
  padding: 8px 12px;
  background: #1a1a2e;
  color: #e0e0ff;
  border: 1px solid #2d2d4a;
  border-radius: 6px;
  font-size: 0.95em;
}

.input-text:focus,
.input-select:focus,
.input-number:focus {
  outline: none;
  border-color: #534ab7;
}

.btn-primary {
  padding: 8px 20px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.95em;
  transition: background 0.2s;
}

.btn-primary:hover {
  background: #6b5cc4;
}

.api-keys-list {
  margin-top: 24px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.range-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85em;
  color: #888;
}

.input-select-small {
  padding: 4px 8px;
  background: #1a1a2e;
  color: #e0e0ff;
  border: 1px solid #2d2d4a;
  border-radius: 4px;
  font-size: 0.85em;
}

.key-stats {
  margin-top: 12px;
  padding: 10px 12px;
  background: #0f0f1a;
  border-radius: 6px;
  border: 1px solid #2d2d4a;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  padding: 2px 0;
  font-size: 0.82em;
}

.stat-row span:first-child {
  color: #888;
}

.stat-row span:last-child {
  color: #e0e0ff;
  font-weight: 500;
}

.empty-state {
  padding: 32px;
  text-align: center;
  opacity: 0.6;
  border: 2px dashed #2d2d4a;
  border-radius: 8px;
}

.api-key-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: #1a1a2e;
  border-radius: 8px;
  margin-bottom: 12px;
  border: 1px solid #2d2d4a;
}

.key-info {
  flex: 1;
  min-width: 200px;
}

.key-name {
  font-weight: bold;
  font-size: 1.1em;
  color: #7c5cff;
}

.key-meta {
  font-size: 0.85em;
  opacity: 0.7;
  margin-top: 4px;
}

.key-scopes {
  margin-top: 8px;
}

.scope-badge {
  display: inline-block;
  padding: 2px 8px;
  background: #2d2d4a;
  border-radius: 4px;
  font-size: 0.8em;
  margin-right: 4px;
}

.key-actions {
  display: flex;
  gap: 8px;
}

.btn-secondary {
  padding: 6px 12px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}

.btn-secondary:hover:not(:disabled) {
  background: #3d3d5a;
}

.btn-secondary:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-warning {
  padding: 6px 12px;
  background: #5a3a1a;
  color: #fbbf24;
  border: 1px solid #fbbf24;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}

.btn-warning:hover {
  background: #7a4a2a;
}

.btn-danger {
  padding: 6px 12px;
  background: #5a1a1a;
  color: #f44336;
  border: 1px solid #f44336;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}

.btn-danger:hover {
  background: #7a2a2a;
}

.message {
  padding: 12px 16px;
  border-radius: 6px;
  margin: 16px 0;
  font-size: 0.95em;
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
}

.message.success {
  background: #1a3a1a;
  color: #4caf50;
  border: 1px solid #2d4a2d;
}

.message.error {
  background: #3a1a1a;
  color: #f44336;
  border: 1px solid #4a2d2d;
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #1a1a2e;
  border: 1px solid #534ab7;
  border-radius: 12px;
  padding: 24px;
  max-width: 500px;
  width: 90%;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #2d2d4a;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.2em;
  color: #7c5cff;
}

.modal-close {
  background: none;
  border: none;
  color: #e0e0ff;
  font-size: 1.5em;
  cursor: pointer;
  padding: 0 8px;
  line-height: 1;
}

.modal-close:hover {
  color: #f44336;
}

.modal-body {
  margin-bottom: 16px;
}

.modal-body p {
  color: #fbbf24;
  font-size: 0.9em;
  margin: 0 0 16px 0;
}

.key-display {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #0d0d1a;
  border: 1px solid #2d2d4a;
  border-radius: 8px;
}

.key-display code {
  flex: 1;
  font-size: 0.95em;
  color: #4caf50;
  word-break: break-all;
  user-select: all;
}

.btn-copy-key {
  padding: 8px 16px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9em;
  white-space: nowrap;
  flex-shrink: 0;
}

.btn-copy-key:hover {
  background: #6b5cc4;
}

.modal-large {
  max-width: 800px;
  width: 95%;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-large .modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.detail-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85em;
}

.detail-table th {
  text-align: left;
  padding: 8px;
  border-bottom: 2px solid #2d2d4a;
  color: #888;
  font-weight: 600;
  position: sticky;
  top: 0;
  background: #1a1a2e;
}

.detail-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #1a1a2e;
  color: #c0c0e0;
}

.detail-table tr.status-ok:hover { background: rgba(52, 211, 153, 0.05); }
.detail-table tr.status-err:hover { background: rgba(248, 113, 113, 0.05); }

.method-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.85em;
  font-weight: 600;
}

.method-badge.GET { color: #60a5fa; background: rgba(96, 165, 250, 0.1); }
.method-badge.POST { color: #34d399; background: rgba(52, 211, 153, 0.1); }
.method-badge.PUT { color: #fbbf24; background: rgba(251, 191, 36, 0.1); }
.method-badge.DELETE { color: #f87171; background: rgba(248, 113, 113, 0.1); }

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
