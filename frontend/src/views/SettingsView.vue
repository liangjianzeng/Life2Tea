<template>
  <div class="settings-view">
    <h2>{{ t("settings.title") }}</h2>

    <div class="settings-section">
      <h3>{{ t("settings.section.paths") }}</h3>
      <div class="form-group">
        <label>{{ t("settings.labels.modelsDir") }}</label>
        <input v-model="config.models_dir" :placeholder="t('settings.labels.modelsDir')" />
      </div>
      <div class="form-group">
        <label>{{ t("settings.labels.backendDir") }}</label>
        <input v-model="config.llama_backend_dir" :placeholder="t('settings.labels.backendDir')" />
      </div>
      <div class="form-group">
        <label>{{ t("settings.labels.serverExe") }}</label>
        <input v-model="config.llama_server_exe" :placeholder="t('settings.labels.serverExe')" />
      </div>
    </div>

    <div class="settings-section">
      <h3>{{ t("settings.section.modelDefaults") }}</h3>
      <div class="form-group">
        <label>{{ t("settings.labels.gpuLayers") }}</label>
        <input v-model.number="config.gpu_layers" type="number" min="0" max="999" />
      </div>
      <div class="form-group">
        <label>{{ t("settings.labels.ctxSize") }}</label>
        <input v-model.number="config.ctx_size" type="number" min="512" max="131072" />
      </div>
      <div class="form-group">
        <label>{{ t("settings.labels.threads") }}</label>
        <input v-model.number="config.threads" type="number" min="1" max="32" />
      </div>
      <div class="form-group">
        <label>{{ t("settings.labels.batchSize") }}</label>
        <input v-model.number="config.batch_size" type="number" min="1" max="4096" />
      </div>
    </div>

    <div class="settings-section">
      <h3>{{ t("settings.section.backendOptions") }}</h3>
      <div class="form-group">
        <label>{{ t("settings.labels.backendPref") }}</label>
        <select v-model="config.backend_preference">
          <option value="auto">{{ t("settings.backendPref.auto") }}</option>
          <option value="cuda">{{ t("settings.backendPref.cuda") }}</option>
          <option value="vulkan">{{ t("settings.backendPref.vulkan") }}</option>
          <option value="cpu">{{ t("settings.backendPref.cpu") }}</option>
        </select>
      </div>
      <div class="form-group checkbox-group">
        <label>
          <input v-model="config.flash_attn" type="checkbox" />
          {{ t("settings.options.flashAttn") }}
        </label>
      </div>
      <div class="form-group checkbox-group">
        <label>
          <input v-model="config.cont_batching" type="checkbox" />
          {{ t("settings.options.contBatching") }}
        </label>
      </div>
      <div class="form-group checkbox-group">
        <label>
          <input v-model="config.mlock" type="checkbox" />
          {{ t("settings.options.mlock") }}
        </label>
      </div>
      <div class="form-group checkbox-group">
        <label>
          <input v-model="config.mmap" type="checkbox" />
          {{ t("settings.options.mmap") }}
        </label>
      </div>
    </div>

    <div class="settings-actions">
      <button @click="save" :disabled="saving" class="btn-save">
        {{ saving ? t("settings.saving") : t("settings.save") }}
      </button>
      <button @click="reload" :disabled="saving" class="btn-reload">
        {{ t("settings.reload") }}
      </button>
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

const config = ref<any>({});
const saving = ref(false);
const message = ref("");
const messageType = ref<"success" | "error">("success");

async function load() {
  try {
    const res = await fetch("/api/config/global");
    if (!res.ok) throw new Error("Failed to load config");
    config.value = await res.json();
  } catch (e: any) {
    showMessage(t("settings.error", { msg: e.message }), "error");
  }
}

async function save() {
  saving.value = true;
  try {
    const res = await fetch("/api/config/global", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config.value),
    });
    const data = await res.json();
    if (data.ok) {
      showMessage(t("settings.saved"), "success");
    } else {
      showMessage(t("settings.error", { msg: data.error || "Unknown error" }), "error");
    }
  } catch (e: any) {
    showMessage(t("settings.error", { msg: e.message }), "error");
  } finally {
    saving.value = false;
  }
}

function reload() {
  load();
  showMessage(t("settings.reloaded"), "success");
}

function showMessage(text: string, type: "success" | "error") {
  message.value = text;
  messageType.value = type;
  setTimeout(() => {
    message.value = "";
  }, 3000);
}

onMounted(load);
</script>

<style scoped>
.settings-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 16px;
  height: 100%;
  overflow-y: auto;
}

h2 {
  margin: 0;
  padding: 16px 0;
  border-bottom: 1px solid #2d2d4a;
  font-size: 1.2em;
}

.settings-section {
  margin: 24px 0;
  padding-bottom: 16px;
  border-bottom: 1px solid #2d2d4a;
}

.settings-section:last-of-type {
  border-bottom: none;
}

.settings-section h3 {
  margin: 0 0 12px 0;
  font-size: 1em;
  opacity: 0.8;
}

.form-group {
  margin: 8px 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-group label {
  min-width: 180px;
  font-size: 0.9em;
  opacity: 0.7;
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group select {
  flex: 1;
  max-width: 400px;
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

.settings-actions {
  display: flex;
  gap: 12px;
  margin: 24px 0;
}

.btn-save {
  padding: 8px 20px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.95em;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-save:hover:not(:disabled) {
  background: #6b5cc4;
}

.btn-reload {
  padding: 8px 20px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.95em;
}

.btn-reload:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-reload:hover:not(:disabled) {
  background: #3d3d5a;
}

.message {
  padding: 10px 16px;
  border-radius: 6px;
  margin: 16px 0;
  font-size: 0.9em;
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
