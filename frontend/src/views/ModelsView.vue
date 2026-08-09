<template>
  <div class="models-view">
    <div class="models-header">
      <h2>{{ t("models.title") }}</h2>
      <div class="header-actions">
        <button @click="scan" :disabled="scanning" class="btn-scan">
          {{ scanning ? t("models.scanning") : t("models.scan") }}
        </button>
      </div>
    </div>
    <div v-if="providers.length" class="models-list">
      <div v-for="m in providers" :key="m.family" class="model-card">
        <div class="model-info">
          <strong class="model-name">{{ m.display }}</strong>
          <span class="model-meta">{{ m.provider }} · :{{ m.port }}</span>
          <span v-if="m.status === 'running'" class="model-status running">
            {{ t("models.running", { port: m.port }) }}
          </span>
          <span v-else class="model-status stopped">{{ t("models.stopped") }}</span>
        </div>
        <div class="model-actions">
          <button
            v-if="m.status !== 'running'"
            @click="loadModel(m)"
            :disabled="loadingModel === m.family"
            class="btn-load"
          >
            {{ loadingModel === m.family ? t("models.loading") : t("models.load") }}
          </button>
          <button
            v-else
            @click="unloadModel(m)"
            :disabled="loadingModel === m.family"
            class="btn-unload"
          >
            {{ loadingModel === m.family ? t("models.unloading") : t("models.unload") }}
          </button>
          <button @click="showConfig(m)" class="btn-config">
            ⚙️ {{ t("models.config") }}
          </button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>{{ t("models.none") }}</p>
      <p class="hint">{{ t("models.hint") }}</p>
    </div>
    <!-- Provider Params Modal (generic key/value editor) -->
    <div v-if="showConfigModal" class="modal-overlay" @click.self="closeConfig">
      <div class="modal-content config-modal">
        <div class="modal-header">
          <h3>{{ t("models.configTitle", { model: selectedModel?.display }) }}</h3>
          <button class="modal-close" @click="closeConfig">&times;</button>
        </div>
        <div class="modal-body">
          <p class="mtp-description"><p>{{ t("models.configHint") }}</p></p>
          <div class="config-section">
            <div v-for="(v, k) in modelConfig" :key="k" class="form-group">
              <label>{{ k }}</label>
              <input v-if="typeof v === 'boolean'"
                     type="checkbox" :checked="modelConfig[k]" @change="modelConfig[k] = !modelConfig[k]" />
              <input v-else-if="typeof v === 'number'"
                     v-model.number="modelConfig[k]" type="number" step="any" />
              <input v-else v-model="modelConfig[k]" type="text" />
            </div>
          </div>
          <div class="config-section">
            <h4>{{ t("models.configAdd") }}</h4>
            <div class="form-group">
              <label>{{ t("models.configAddKey") }}</label>
              <input v-model="newParamKey" type="text" placeholder="key" />
            </div>
            <div class="form-group">
              <label>{{ t("models.configAddValue") }}</label>
              <input v-model="newParamValue" type="text" placeholder="value" />
              <button class="btn-preset" @click="addParam">+</button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="closeConfig">{{ t("settings.picker.cancel") }}</button>
          <button class="btn-save" @click="saveModelConfig">{{ t("settings.save") }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { storeToRefs } from "pinia";
import { useGatewayStore } from "../stores/gateway";
import { getModelParams } from "../api/models";
import type { ModelEndpoint } from "../types";

const { t } = useI18n();
const store = useGatewayStore();
const { providers } = storeToRefs(store);

const scanning = ref(false);
const loadingModel = ref<string | null>(null);
const showConfigModal = ref(false);
const selectedModel = ref<ModelEndpoint | null>(null);
const modelConfig = ref<Record<string, any>>({});
const newParamKey = ref("");
const newParamValue = ref("");

async function scan() {
  scanning.value = true;
  try {
    await store.rescan();
  } catch (e) {
    alert(t("models.errorScan"));
  } finally {
    scanning.value = false;
  }
}

async function loadModel(m: ModelEndpoint) {
  loadingModel.value = m.family;
  try {
    await store.start(m.family);
  } catch (e: any) {
    alert(t("models.errorLoad", { msg: e.message }));
  } finally {
    loadingModel.value = null;
  }
}

async function unloadModel(m: ModelEndpoint) {
  if (!confirm(t("models.confirmUnload", { name: m.display }))) return;
  loadingModel.value = m.family;
  try {
    await store.stop(m.family);
  } catch (e: any) {
    alert(t("models.errorUnload", { msg: e.message }));
  } finally {
    loadingModel.value = null;
  }
}

async function refresh() {
  await store.refresh();
}

async function showConfig(m: ModelEndpoint) {
  selectedModel.value = m;
  showConfigModal.value = true;
  newParamKey.value = "";
  newParamValue.value = "";
  try {
    const params = await getModelParams(m.family);
    modelConfig.value = { ...params };
  } catch {
    modelConfig.value = {};
  }
}

function closeConfig() {
  showConfigModal.value = false;
  selectedModel.value = null;
}

function addParam() {
  const key = newParamKey.value.trim();
  if (!key) return;
  const raw = newParamValue.value.trim();
  let val: any = raw;
  if (/^-?\d+$/.test(raw)) val = parseInt(raw, 10);
  else if (/^-?\d+\.\d+$/.test(raw)) val = parseFloat(raw);
  else if (raw === "true") val = true;
  else if (raw === "false") val = false;
  modelConfig.value[key] = val;
  newParamKey.value = "";
  newParamValue.value = "";
}

async function saveModelConfig() {
  if (!selectedModel.value) return;
  try {
    const res = await fetch(`/api/models/${selectedModel.value.family}/params`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: modelConfig.value }),
      credentials: "include",
    });
    if (res.ok) {
      closeConfig();
      await store.refresh();
      alert(t("models.configSaved"));
    } else {
      alert(t("models.configError"));
    }
  } catch (e) {
    alert(t("models.configError"));
  }
}

onMounted(scan);
</script>
<style scoped>
.ctx-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ctx-input-wrap input {
  width: 80px;
}
.ctx-unit {
  color: #888;
  font-size: 14px;
  font-weight: 500;
}
.models-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.models-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
  border-bottom: 1px solid #2d2d4a;
}
.models-header h2 {
  margin: 0;
  font-size: 1.2em;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.btn-scan {
  padding: 6px 16px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-scan:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.models-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.model-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #1a1a2e;
  border-radius: 8px;
  border: 1px solid #2d2d4a;
}
.model-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.model-name {
  color: #e0e0ff;
  font-size: 1em;
}
.model-meta {
  font-size: 0.85em;
  opacity: 0.6;
}
.model-status {
  font-size: 0.8em;
  padding: 2px 8px;
  border-radius: 12px;
  width: fit-content;
}
.model-status.running {
  background: #1a3a1a;
  color: #4caf50;
}
.model-status.stopped {
  background: #3a1a1a;
  color: #f44336;
}
.model-disabled {
  font-size: 0.75em;
  padding: 2px 6px;
  border-radius: 4px;
  background: #555;
  color: #aaa;
  margin-top: 2px;
  display: inline-block;
}
.model-actions {
  display: flex;
  gap: 8px;
}
.btn-load {
  padding: 6px 16px;
  background: #4caf50;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-load:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-unload {
  padding: 6px 16px;
  background: #f44336;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-config {
  padding: 6px 12px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-config:hover {
  background: #6b5cc4;
}
.btn-disable {
  padding: 6px 12px;
  background: #ff9800;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}
.btn-enable {
  padding: 6px 12px;
  background: #4caf50;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-enable:hover,
.btn-disable:hover {
  opacity: 0.9;
}
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.config-modal {
  width: 600px;
  max-width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  background: #1a1a2e;
  border: 1px solid #534ab7;
  border-radius: 12px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
}
.config-section {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid #2d2d4a;
}
.config-section:last-child {
  border-bottom: none;
}
.config-section h4 {
  margin: 0 0 12px 0;
  color: #7c5cff;
  font-size: 1em;
}
.form-group {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}
.form-group label {
  min-width: 140px;
  font-size: 0.85em;
  color: #b0b0d0;
}
.form-group input[type="number"],
.form-group select {
  flex: 1;
  max-width: 200px;
  padding: 6px 10px;
  background: #1a1a2e;
  color: #e0e0ff;
  border: 1px solid #2d2d4a;
  border-radius: 4px;
  font-size: 0.9em;
}
.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #534ab7;
}
.checkbox-group {
  display: flex;
  align-items: center;
}
.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  min-width: auto;
}
.checkbox-group input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}
.preset-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.mtp-description {
  margin-bottom: 15px;
  padding: 10px;
  background: #1a1a2e;
  border: 1px solid #2d2d4a;
  border-radius: 4px;
}
.mtp-description p {
  margin: 0;
  font-size: 0.85em;
  color: #a0a0c0;
  line-height: 1.4;
}
.mtp-params {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px dashed #2d2d4a;
}
.param-hint {
  display: block;
  margin-top: 4px;
  font-size: 0.75em;
  color: #666;
  font-style: italic;
}
.btn-preset {
  padding: 6px 12px;
  background: #2d2d4a;
  color: #7c5cff;
  border: 1px solid #534ab7;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}
.btn-preset:hover {
  background: #3d3d5a;
  color: #9d7fff;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 0 0 0;
  border-top: 1px solid #2d2d4a;
  margin-top: 20px;
}
.btn-cancel {
  padding: 8px 16px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-cancel:hover {
  background: #3d3d5a;
}
.btn-save {
  padding: 8px 16px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-save:hover {
  background: #6b5cc4;
}
.btn-unload:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  opacity: 0.6;
  text-align: center;
}
.hint {
  font-size: 0.9em;
  max-width: 400px;
}
code {
  background: #2d2d4a;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
</style>
