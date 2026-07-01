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
    <div v-if="models.length" class="models-list">
      <div v-for="m in models" :key="m.family" class="model-card">
        <div class="model-info">
          <strong class="model-name">{{ m.display }}</strong>
          <span class="model-meta">{{ m.size_gb }} GB · {{ m.quantization }}</span>
          <span v-if="m.instance" class="model-status running">
            {{ t("models.running", { port: m.instance.port }) }}
          </span>
          <span v-else class="model-status stopped">{{ t("models.stopped") }}</span>
          <span v-if="m.disabled" class="model-disabled">已禁用</span>
        </div>
        <div class="model-actions">
          <button
            v-if="!m.instance && !m.disabled"
            @click="loadModel(m)"
            :disabled="loadingModel === m.family"
            class="btn-load"
          >
            {{ loadingModel === m.family ? t("models.loading") : t("models.load") }}
          </button>
          <button
            v-else-if="!m.instance && m.disabled"
            @click="enableModel(m)"
            :disabled="loadingModel === m.family"
            class="btn-enable"
          >
            启用模型
          </button>
          <button
            v-else-if="m.instance"
            @click="unloadModel(m)"
            :disabled="loadingModel === m.family"
            class="btn-unload"
          >
            {{ loadingModel === m.family ? t("models.unloading") : t("models.unload") }}
          </button>
          <button @click="showConfig(m)" class="btn-config">
            ⚙️ 配置
          </button>
          <button
            v-if="!m.disabled"
            @click="disableModel(m)"
            class="btn-disable"
            title="禁用模型（防止自动加载）"
          >
            禁用
          </button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>{{ t("models.none") }}</p>
      <p class="hint">{{ t("models.hint", { path: "`models_dir`" }) }}</p>
    </div>
    <!-- Model Config Modal -->
    <div v-if="showConfigModal" class="modal-overlay" @click.self="closeConfig">
      <div class="modal-content config-modal">
        <div class="modal-header">
          <h3>{{ t("models.configTitle", { model: selectedModel?.display }) }}</h3>
          <button class="modal-close" @click="closeConfig">&times;</button>
        </div>
        <div class="modal-body">
          <div class="config-section">
            <h4>{{ t("models.configMemory") }}</h4>
            <div class="form-group">
              <label>{{ t("settings.labels.gpuLayers") }}</label>
              <input v-model.number="modelConfig.gpu_layers" type="number" min="0" max="999" />
            </div>
            <div class="form-group">
              <label>{{ t("settings.labels.ctxSize") }}</label>
              <div class="ctx-input-wrap">
                <input v-model.number="ctx_size_k" type="number" min="1" max="128" step="1" />
                <span class="ctx-unit">K</span>
              </div>
            </div>
            <div class="form-group">
              <label>{{ t("settings.labels.threads") }}</label>
              <input v-model.number="modelConfig.threads" type="number" min="1" max="32" />
            </div>
            <div class="form-group">
              <label>{{ t("settings.labels.batchSize") }}</label>
              <input v-model.number="modelConfig.batch_size" type="number" min="1" max="4096" />
            </div>
          </div>
          <div class="config-section">
            <h4>{{ t("models.configAdvanced") }}</h4>
            <div class="form-group checkbox-group">
              <label>
                <input v-model="modelConfig.flash_attn" type="checkbox" />
                {{ t("settings.options.flashAttn") }}
              </label>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input v-model="modelConfig.cont_batching" type="checkbox" />
                {{ t("settings.options.contBatching") }}
              </label>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input v-model="modelConfig.mmap" type="checkbox" />
                {{ t("settings.options.mmap") }}
              </label>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input v-model="modelConfig.mlock" type="checkbox" />
                {{ t("settings.options.mlock") }}
              </label>
            </div>
          </div>
          <div class="config-section">
            <h4>{{ t("models.configMTP") }}</h4>
            <div class="mtp-description">
              <p>{{ t("models.mtpDescription") }}</p>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input v-model="modelConfig.mtp_enabled" type="checkbox" />
                {{ t("models.mtpEnabled") }}
              </label>
            </div>
            <div v-if="modelConfig.mtp_enabled" class="mtp-params">
              <div class="form-group">
                <label>{{ t("models.mtpPredictions") }}</label>
                <input v-model.number="modelConfig.mtp_predictions" type="number" min="1" max="20" />
                <span class="param-hint">{{ t("models.mtpPredictionsHint") }}</span>
              </div>
              <div class="form-group">
                <label>{{ t("models.mtpMinTokens") }}</label>
                <input v-model.number="modelConfig.mtp_min_tokens" type="number" min="0" max="1000" />
                <span class="param-hint">{{ t("models.mtpMinTokensHint") }}</span>
              </div>
              <div class="form-group">
                <label>{{ t("models.mtpTemp") }}</label>
                <input v-model.number="modelConfig.mtp_temperature" type="number" min="0" max="2" step="0.1" />
                <span class="param-hint">{{ t("models.mtpTempHint") }}</span>
              </div>
              <div class="form-group">
                <label>{{ t("models.mtpProbThreshold") }}</label>
                <input v-model.number="modelConfig.mtp_prob_threshold" type="number" min="0" max="1" step="0.01" />
                <span class="param-hint">{{ t("models.mtpProbThresholdHint") }}</span>
              </div>
              <div class="form-group">
                <label>{{ t("models.mtpParallel") }}</label>
                <input v-model.number="modelConfig.mtp_parallel" type="number" min="1" max="8" />
                <span class="param-hint">{{ t("models.mtpParallelHint") }}</span>
              </div>
            </div>
          </div>
          <div class="config-section">
            <h4>{{ t("models.configKVCache") }}</h4>
            <div class="form-group">
              <label>{{ t("models.configKVTypeK") }}</label>
              <select v-model="modelConfig.cache_type_k">
                <option value="f16">F16</option>
                <option value="f32">F32</option>
                <option value="q4_0">Q4_0</option>
                <option value="q8_0">Q8_0</option>
              </select>
            </div>
            <div class="form-group">
              <label>{{ t("models.configKVTypeV") }}</label>
              <select v-model="modelConfig.cache_type_v">
                <option value="f16">F16</option>
                <option value="f32">F32</option>
                <option value="q4_0">Q4_0</option>
                <option value="q8_0">Q8_0</option>
              </select>
            </div>
          </div>
          <div class="config-section">
            <h4>{{ t("models.configPresets") }}</h4>
            <div class="preset-buttons">
              <button @click="applyPreset('lightweight')" class="btn-preset">{{ t("models.presetLightweight") }}</button>
              <button @click="applyPreset('balanced')" class="btn-preset">{{ t("models.presetBalanced") }}</button>
              <button @click="applyPreset('highPerformance')" class="btn-preset">{{ t("models.presetHighPerformance") }}</button>
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
import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
interface Model {
  family: string;
  name: string;
  display: string;
  path: string;
  size_gb: number;
  quantization: string;
  params_b: number;
  default_port: number;
  plugin_name: string;
  disabled?: boolean;
  instance: null | {
    plugin_name: string;
    pid: number;
    port: number;
    status: string;
  };
}
const models = ref<Model[]>([]);
const scanning = ref(false);
const loadingModel = ref<string | null>(null);
const showConfigModal = ref(false);
const selectedModel = ref<Model | null>(null);
const modelConfig = ref<any>({
  gpu_layers: 99,
  ctx_size: 32768,
  ctx_size_k: 32,  // K 单位显示值
  threads: 0,
  batch_size: 1024,
  flash_attn: false,
  cont_batching: false,
  mmap: true,
  mlock: false,
  cache_type_k: 'f16',
  cache_type_v: 'f16',
  mtp_enabled: false,
  mtp_predictions: 4,
  mtp_min_tokens: 0,
  mtp_temperature: 1.0,
  mtp_prob_threshold: 0.5,
  mtp_parallel: 1,
});
// ctx_size 显示为 K 单位（32K=32768 tokens）
const ctx_size_k = computed({
  get: () => Math.round((modelConfig.value.ctx_size || 32768) / 1024),
  set: (val: number) => {
    modelConfig.value.ctx_size = val * 1024;
    modelConfig.value.ctx_size_k = val;
  },
});
async function scan() {
  scanning.value = true;
  try {
    const res = await fetch("/api/models/scan", { method: "POST", credentials: "include" });
    const data = await res.json();
    models.value = data.models || [];
  } catch (e) {
    alert(t("models.errorScan"));
  } finally {
    scanning.value = false;
  }
}
async function loadModel(m: Model) {
  loadingModel.value = m.family;
  try {
    const port = m.default_port || 8080;
    const res = await fetch(`/api/models/${m.family}/load`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ port }),
      credentials: "include",
    });
    const data = await res.json();
    if (data.ok) {
      await refresh();
    } else {
      alert(t("models.errorLoad", { msg: data.error || "Unknown error" }));
    }
  } catch (e: any) {
    alert(t("models.errorLoad", { msg: e.message }));
  } finally {
    loadingModel.value = null;
  }
}
async function unloadModel(m: Model) {
  if (!confirm(t("models.confirmUnload", { name: m.display }))) return;
  loadingModel.value = m.family;
  try {
    const res = await fetch(`/api/models/${m.family}/unload`, {
      method: "POST",
      credentials: "include",
    });
    const data = await res.json();
    if (data.ok) {
      await refresh();
    } else {
      alert(t("models.errorUnload", { msg: data.error || "Unknown error" }));
    }
  } catch (e: any) {
    alert(t("models.errorUnload", { msg: e.message }));
  } finally {
    loadingModel.value = null;
  }
}
async function disableModel(m: Model) {
  if (!confirm(`确定要禁用模型 ${m.display} 吗？禁用后不会被系统自动加载。`)) return;
  loadingModel.value = m.family;
  try {
    const res = await fetch(`/api/models/${m.family}/disable`, {
      method: "POST",
      credentials: "include",
    });
    const data = await res.json();
    if (data.ok) {
      await refresh();
      alert(t("models.disabled", { name: m.display }));
    } else {
      alert(t("models.errorDisable", { msg: data.error || "Unknown error" }));
    }
  } catch (e: any) {
    alert(t("models.errorDisable", { msg: e.message }));
  } finally {
    loadingModel.value = null;
  }
}
async function enableModel(m: Model) {
  loadingModel.value = m.family;
  try {
    const res = await fetch(`/api/models/${m.family}/enable`, {
      method: "POST",
      credentials: "include",
    });
    const data = await res.json();
    if (data.ok) {
      await refresh();
      alert(t("models.enabled", { name: m.display }));
    } else {
      alert(t("models.errorEnable", { msg: data.error || "Unknown error" }));
    }
  } catch (e: any) {
    alert(t("models.errorEnable", { msg: e.message }));
  } finally {
    loadingModel.value = null;
  }
}
async function refresh() {
  try {
    const res = await fetch("/api/models", { credentials: "include" });
    const data = await res.json();
    models.value = data.models || [];
    // Debug: log instance status
    console.log("Models with instance:", models.value.filter(m => m.instance));
  } catch (e) {
    console.error("Failed to refresh models:", e);
  }
}
function showConfig(m: Model) {
  selectedModel.value = m;
  showConfigModal.value = true;
  
  // Load existing config or use defaults
  fetch(`/api/config/model-config/${encodeURIComponent(m.family)}`, { credentials: "include" })
    .then(res => {
      if (res.ok) {
        return res.json();
      } else {
        return null;
      }
    })
    .then(data => {
      if (data && data.params) {
        modelConfig.value = { ...modelConfig.value, ...data.params };
      }
    })
    .catch(() => {
      // Use defaults
    });
}
function closeConfig() {
  showConfigModal.value = false;
  selectedModel.value = null;
}
async function saveModelConfig() {
  if (!selectedModel.value) return;
  
  try {
    const res = await fetch(`/api/config/model-config/${encodeURIComponent(selectedModel.value.family)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: modelConfig.value }),
      credentials: "include",
    });
    
    if (res.ok) {
      closeConfig();
      alert(t("models.configSaved"));
    } else {
      alert(t("models.configError"));
    }
  } catch (e) {
    alert(t("models.configError"));
  }
}
function applyPreset(preset: string) {
  switch (preset) {
    case 'lightweight':
      modelConfig.value = {
        gpu_layers: 20,
        ctx_size: 4096,
        ctx_size_k: 4,
        threads: 4,
        batch_size: 512,
        flash_attn: false,
        cont_batching: false,
        mmap: true,
        mlock: false,
        cache_type_k: 'f16',
        cache_type_v: 'f16',
        mtp_enabled: false,
        mtp_predictions: 2,
        mtp_min_tokens: 0,
        mtp_temperature: 1.0,
        mtp_prob_threshold: 0.7,
        mtp_parallel: 1,
      };
      break;
    case 'balanced':
      modelConfig.value = {
        gpu_layers: 40,
        ctx_size: 8192,
        ctx_size_k: 8,
        threads: 8,
        batch_size: 1024,
        flash_attn: true,
        cont_batching: true,
        mmap: true,
        mlock: false,
        cache_type_k: 'f16',
        cache_type_v: 'f16',
        mtp_enabled: true,
        mtp_predictions: 4,
        mtp_min_tokens: 0,
        mtp_temperature: 0.8,
        mtp_prob_threshold: 0.5,
        mtp_parallel: 2,
      };
      break;
    case 'highPerformance':
      modelConfig.value = {
        gpu_layers: 99,
        ctx_size: 16384,
        ctx_size_k: 16,
        threads: 16,
        batch_size: 2048,
        flash_attn: true,
        cont_batching: true,
        mmap: true,
        mlock: true,
        cache_type_k: 'f32',
        cache_type_v: 'f32',
        mtp_enabled: true,
        mtp_predictions: 8,
        mtp_min_tokens: 0,
        mtp_temperature: 0.6,
        mtp_prob_threshold: 0.3,
        mtp_parallel: 4,
      };
      break;
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
