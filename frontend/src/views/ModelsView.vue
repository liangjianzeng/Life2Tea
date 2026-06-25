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
        </div>
        <div class="model-actions">
          <button
            v-if="!m.instance"
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
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <p>{{ t("models.none") }}</p>
      <p class="hint">{{ t("models.hint", { path: "`models_dir`" }) }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
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

async function scan() {
  scanning.value = true;
  try {
    const res = await fetch("/api/models/scan", { method: "POST" });
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

async function refresh() {
  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    models.value = data.models || [];
  } catch (e) {
    // Ignore
  }
}

onMounted(scan);
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
