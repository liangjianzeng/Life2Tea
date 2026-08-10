<template>
  <div class="models-view">
    <div class="models-header">
      <h2>{{ t("models.title") }}</h2>
      <div class="header-actions">
        <button @click="openNew" class="btn-add">{{ t("models.add") }}</button>
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
          <div class="status-row">
            <span v-if="m.disabled" class="model-disabled">{{ t("models.disabledTag") }}</span>
            <span v-if="m.status === 'running'" class="model-status running">
              {{ t("models.running", { port: m.port }) }}
            </span>
            <span v-else class="model-status stopped">{{ t("models.stopped") }}</span>
          </div>
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
          <button v-if="m.disabled" @click="toggleDisable(m)" class="btn-enable">
            {{ t("models.enable") }}
          </button>
          <button v-else @click="toggleDisable(m)" class="btn-disable">
            {{ t("models.disable") }}
          </button>
          <button @click="showConfig(m)" class="btn-config">⚙️ {{ t("models.config") }}</button>
          <button @click="removeModel(m)" class="btn-danger">{{ t("models.delete") }}</button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>{{ t("models.none") }}</p>
      <p class="hint">{{ t("models.hint") }}</p>
    </div>

    <!-- Provider Config Modal (field-based form) -->
    <div v-if="showConfigModal" class="modal-overlay" @click.self="closeConfig">
      <div class="modal-content config-modal">
        <div class="modal-header">
          <h3>{{ isNew ? t("models.addTitle") : t("models.configTitle", { model: editingModel?.display }) }}</h3>
          <button class="modal-close" @click="closeConfig">&times;</button>
        </div>
        <div class="modal-body">
          <div class="config-section">
            <h4>{{ t("models.configBasic") }}</h4>
            <div class="form-group">
              <label>{{ t("models.family") }}</label>
              <input v-model="form.family" type="text" :disabled="!isNew" />
            </div>
            <div class="form-group">
              <label>{{ t("models.provider") }}</label>
              <select v-model="form.provider" @change="applyProviderSchema">
                <option v-for="b in backends" :key="b.kind" :value="b.kind">{{ b.label }}</option>
              </select>
            </div>
            <div v-for="f in currentSchema.core" :key="f.key" class="form-group">
              <label>{{ f.label }}<span v-if="f.required" class="required">*</span></label>
              <template v-if="f.type === 'path'">
                <div class="path-row">
                  <input v-model="form[f.key]" type="text" />
                  <button class="btn-preset" @click="openPathPicker(f.key)">{{ t("models.browse") }}</button>
                </div>
              </template>
              <input v-else-if="f.type === 'number'" v-model.number="form[f.key]" type="number" />
              <input v-else v-model="form[f.key]" type="text" />
            </div>
            <div class="form-group">
              <label>{{ t("models.disabled") }}</label>
              <input v-model="form.disabled" type="checkbox" />
            </div>
          </div>

          <div class="config-section">
            <h4>{{ t("models.configParams") }}</h4>
            <div v-for="f in currentSchema.params" :key="f.key" class="form-group">
              <label>{{ f.label }}</label>
              <input
                v-if="f.type === 'boolean'"
                type="checkbox"
                :checked="!!schemaParams[f.key]"
                @change="schemaParams[f.key] = !schemaParams[f.key]"
              />
              <input
                v-else-if="f.type === 'number'"
                v-model.number="schemaParams[f.key]"
                type="number"
                step="any"
              />
              <input v-else v-model="schemaParams[f.key]" type="text" />
            </div>
          </div>

          <div class="config-section">
            <h4>{{ t("models.configAdvanced") }}</h4>
            <div v-for="(v, k) in customParams" :key="k" class="form-group param-row">
              <label>{{ k }}</label>
              <input
                v-if="typeof v === 'boolean'"
                type="checkbox"
                :checked="v"
                @change="customParams[k] = !customParams[k]"
              />
              <input v-else v-model="customParams[k]" type="text" />
              <button class="btn-preset" @click="removeParam(k)">&times;</button>
            </div>
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
          <button class="btn-save" :disabled="saving" @click="saveConfig">
            {{ saving ? t("models.saving") : t("settings.save") }}
          </button>
        </div>
      </div>
    </div>

    <PathPickerModal
      v-model="showPathPicker"
      title=""
      :initial-path="form.model_path || ''"
      :allow-file="true"
      path-type="executable"
      @select="onPathSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { storeToRefs } from "pinia";
import { useGatewayStore } from "../stores/gateway";
import {
  getModelParams, listBackends, createModel, updateModel, deleteModel,
  disableModel, enableModel,
} from "../api/models";
import PathPickerModal from "../components/PathPickerModal.vue";
import type { ModelEndpoint, ModelConfig, ProviderKind, ProviderSchema } from "../types";

const { t } = useI18n();
const store = useGatewayStore();
const { providers } = storeToRefs(store);

const scanning = ref(false);
const saving = ref(false);
const loadingModel = ref<string | null>(null);
const showConfigModal = ref(false);
const editingModel = ref<ModelEndpoint | null>(null);
const backends = ref<{ kind: string; label: string; schema: ProviderSchema }[]>([]);
const showPathPicker = ref(false);

const form = reactive<Record<string, any>>({
  family: "",
  provider: "llamacpp",
  host: "127.0.0.1",
  port: 8080,
  model_path: "",
  model_name: "",
  disabled: false,
});

const schemaParams = reactive<Record<string, any>>({});
const customParams = reactive<Record<string, any>>({});
const newParamKey = ref("");
const newParamValue = ref("");

const isNew = computed(() => !editingModel.value);
const currentSchema = computed<ProviderSchema>(
  () => backends.value.find((b) => b.kind === form.provider)?.schema || { core: [], params: [] },
);

async function loadBackends() {
  try {
    backends.value = await listBackends();
  } catch {
    backends.value = [];
  }
}

function applyProviderSchema() {
  const schema = currentSchema.value;
  const np: Record<string, any> = {};
  for (const f of schema.params) {
    np[f.key] = f.default ?? "";
  }
  Object.keys(schemaParams).forEach((k) => delete schemaParams[k]);
  Object.assign(schemaParams, np);
}

function openNew() {
  editingModel.value = null;
  Object.assign(form, {
    family: "",
    provider: "llamacpp",
    host: "127.0.0.1",
    port: 8080,
    model_path: "",
    model_name: "",
    disabled: false,
  });
  Object.keys(customParams).forEach((k) => delete customParams[k]);
  applyProviderSchema();
  showConfigModal.value = true;
}

async function showConfig(m: ModelEndpoint) {
  editingModel.value = m;
  Object.assign(form, {
    family: m.family,
    provider: m.provider,
    host: m.host,
    port: m.port,
    model_path: m.model_path,
    model_name: m.model_name,
    disabled: !!m.disabled,
  });
  Object.keys(customParams).forEach((k) => delete customParams[k]);
  try {
    const params = await getModelParams(m.family);
    const schema = currentSchema.value;
    const sp: Record<string, any> = {};
    for (const f of schema.params) {
      if (f.key in params) sp[f.key] = params[f.key];
      else sp[f.key] = f.default ?? "";
    }
    Object.keys(schemaParams).forEach((k) => delete schemaParams[k]);
    Object.assign(schemaParams, sp);
    for (const [k, v] of Object.entries(params)) {
      if (!(k in sp)) customParams[k] = v;
    }
  } catch {
    applyProviderSchema();
  }
  showConfigModal.value = true;
}

function closeConfig() {
  showConfigModal.value = false;
  editingModel.value = null;
}

function openPathPicker(fieldKey: string) {
  showPathPicker.value = true;
}

function onPathSelected(path: string) {
  form.model_path = path;
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
  customParams[key] = val;
  newParamKey.value = "";
  newParamValue.value = "";
}

function removeParam(key: string) {
  delete customParams[key];
}

async function saveConfig() {
  if (isNew.value && !form.family.trim()) {
    alert(t("models.errorFamilyRequired"));
    return;
  }
  saving.value = true;
  try {
    const params = { ...schemaParams, ...customParams };
    const config: ModelConfig = {
      provider: form.provider,
      host: form.host,
      port: form.port,
      params,
    };
    if (form.model_path) config.model_path = form.model_path;
    if (form.model_name) config.model_name = form.model_name;
    if (form.disabled) config.disabled = true;
    if (isNew.value) {
      await createModel(form.family.trim(), config);
    } else {
      await updateModel(editingModel.value!.family, config);
    }
    closeConfig();
    await store.refresh();
    alert(t("models.configSaved"));
  } catch (e: any) {
    alert(t("models.configError") + (e?.message ? `: ${e.message}` : ""));
  } finally {
    saving.value = false;
  }
}

async function removeModel(m: ModelEndpoint) {
  if (!confirm(t("models.confirmDelete", { name: m.display }))) return;
  try {
    await deleteModel(m.family);
    await store.refresh();
  } catch (e: any) {
    alert(t("models.errorDelete", { msg: e?.message }));
  }
}

async function toggleDisable(m: ModelEndpoint) {
  try {
    if (m.disabled) await enableModel(m.family);
    else await disableModel(m.family);
    await store.refresh();
  } catch (e: any) {
    alert(t("models.errorToggle", { msg: e?.message }));
  }
}

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

onMounted(() => {
  loadBackends();
  scan();
});
</script>

<style scoped>
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
.btn-add,
.btn-scan {
  padding: 6px 16px;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.btn-add {
  background: #4caf50;
}
.btn-scan {
  background: #534ab7;
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
.status-row {
  display: flex;
  gap: 6px;
  align-items: center;
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
  display: inline-block;
}
.model-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.btn-load,
.btn-enable {
  padding: 6px 12px;
  background: #4caf50;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}
.btn-unload,
.btn-danger {
  padding: 6px 12px;
  background: #f44336;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}
.btn-config {
  padding: 6px 12px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
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
.btn-load:disabled,
.btn-unload:disabled,
.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
  width: 640px;
  max-width: 90%;
  max-height: 85vh;
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
  gap: 8px;
}
.form-group label {
  min-width: 150px;
  font-size: 0.85em;
  color: #b0b0d0;
}
.required {
  color: #f44336;
  margin-left: 2px;
}
.form-group input[type="number"],
.form-group input[type="text"],
.form-group select {
  flex: 1;
  max-width: 280px;
  padding: 6px 10px;
  background: #1a1a2e;
  color: #e0e0ff;
  border: 1px solid #2d2d4a;
  border-radius: 4px;
  font-size: 0.9em;
}
.form-group input:disabled {
  opacity: 0.5;
}
.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: #534ab7;
}
.path-row {
  flex: 1;
  max-width: 280px;
  display: flex;
  gap: 4px;
}
.path-row input {
  flex: 1;
  max-width: 220px;
}
.param-row label {
  min-width: 120px;
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
.btn-save {
  padding: 8px 16px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
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
</style>
