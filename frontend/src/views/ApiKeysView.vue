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
      <h3>{{ t("settings.apiKeys.title") }}</h3>
      <div v-if="keys.length === 0" class="empty-state">
        {{ t("settings.apiKeys.none") }}
      </div>
      <div v-for="key in keys" :key="key.id" class="api-key-item">
        <div class="key-info">
          <div class="key-name">{{ key.name }}</div>
          <div class="key-meta">
            <span>创建: {{ formatDate(key.created_at_iso) }}</span>
            <span v-if="key.expires_at_iso">过期: {{ formatDate(key.expires_at_iso) }}</span>
            <span>剩余: {{ key.remaining_days }} 天</span>
          </div>
          <div class="key-scopes">
            <span v-for="scope in key.scopes" :key="scope" class="scope-badge">{{ scope }}</span>
          </div>
        </div>
        <div class="key-actions">
          <button
            @click="copyKey(key.id)"
            class="btn-secondary"
            title="复制密钥（仅创建时显示）"
            :disabled="!key.key"
          >
            复制
          </button>
          <button
            @click="revokeKey(key.id)"
            class="btn-warning"
            title="撤销密钥"
          >
            撤销
          </button>
          <button
            @click="deleteKey(key.id)"
            class="btn-danger"
            title="删除密钥"
          >
            删除
          </button>
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
const newKey = ref({
  name: "",
  scopes: [] as string[],
  expires: 0,
});
const message = ref("");
const messageType = ref<"success" | "error">("success");

async function loadKeys() {
  try {
    const res = await fetch("/api/keys");
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
  try {
    const res = await fetch("/api/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newKey.value.name,
        scopes: newKey.value.scopes,
        expires_in_days: newKey.value.expires || null,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      showMessage(t("settings.apiKeys.successCreate"), "success");
      // Show the plain key once
      if (data.key) {
        showMessage(t("settings.apiKeys.keyCreated", { key: data.key }), "success");
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
    const res = await fetch(`/api/keys/${keyId}`, { method: "DELETE" });
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
    const res = await fetch(`/api/keys/${keyId}/revoke`, { method: "POST" });
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

onMounted(loadKeys);
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
</style>
