<template>
  <div class="plugins-view">
    <div class="plugins-header">
      <h2>Plugins</h2>
      <button @click="refresh" :disabled="loading" class="btn-refresh">
        {{ loading ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <div v-if="plugins.length" class="plugins-list">
      <div v-for="p in plugins" :key="p.family" class="plugin-card">
        <div class="plugin-info">
          <strong class="plugin-name">{{ p.display }}</strong>
          <span class="plugin-type">{{ p.plugin_type || 'model' }}</span>
          <span v-if="p.instance" class="plugin-status running">
            Running on port {{ p.instance.port }}
          </span>
          <span v-else class="plugin-status stopped">Stopped</span>
        </div>
        <div class="plugin-actions">
          <button
            v-if="!p.instance"
            @click="loadPlugin(p)"
            :disabled="loadingPlugin === p.family"
            class="btn-load"
          >
            {{ loadingPlugin === p.family ? 'Loading...' : 'Load' }}
          </button>
          <button
            v-else
            @click="unloadPlugin(p)"
            :disabled="loadingPlugin === p.family"
            class="btn-unload"
          >
            {{ loadingPlugin === p.family ? 'Unloading...' : 'Unload' }}
          </button>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <p>No plugins found.</p>
      <p class="hint">Scan models in Settings to discover plugins.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

interface Plugin {
  family: string;
  name: string;
  display: string;
  path: string;
  size_gb: number;
  quantization: string;
  params_b: number;
  default_port: number;
  plugin_name: string;
  plugin_type?: string;
  instance: null | {
    plugin_name: string;
    plugin_type: string;
    pid: number;
    port: number;
    status: string;
  };
}

const plugins = ref<Plugin[]>([]);
const loading = ref(false);
const loadingPlugin = ref<string | null>(null);

async function refresh() {
  loading.value = true;
  try {
    const res = await fetch("/api/plugins");
    const data = await res.json();
    plugins.value = data.plugins || [];
  } catch (e) {
    alert("Failed to load plugins");
  } finally {
    loading.value = false;
  }
}

async function loadPlugin(p: Plugin) {
  loadingPlugin.value = p.family;
  try {
    const port = p.default_port || 8080;
    const res = await fetch(`/api/plugins/${p.family}/load`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ port }),
    });
    const data = await res.json();
    if (data.ok) {
      await refresh();
    } else {
      alert(`Failed to load plugin: ${data.error || "Unknown error"}`);
    }
  } catch (e: any) {
    alert(`Error: ${e.message}`);
  } finally {
    loadingPlugin.value = null;
  }
}

async function unloadPlugin(p: Plugin) {
  if (!confirm(`Unload ${p.display}?`)) return;

  loadingPlugin.value = p.family;
  try {
    const res = await fetch(`/api/plugins/${p.family}/unload`, {
      method: "POST",
    });
    const data = await res.json();
    if (data.ok) {
      await refresh();
    } else {
      alert(`Failed to unload plugin: ${data.error || "Unknown error"}`);
    }
  } catch (e: any) {
    alert(`Error: ${e.message}`);
  } finally {
    loadingPlugin.value = null;
  }
}

onMounted(refresh);
</script>

<style scoped>
.plugins-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.plugins-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
  border-bottom: 1px solid #2d2d4a;
}

.plugins-header h2 {
  margin: 0;
  font-size: 1.2em;
}

.btn-refresh {
  padding: 6px 16px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.plugins-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plugin-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #1a1a2e;
  border-radius: 8px;
  border: 1px solid #2d2d4a;
}

.plugin-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.plugin-name {
  color: #e0e0ff;
  font-size: 1em;
}

.plugin-type {
  font-size: 0.8em;
  opacity: 0.6;
  text-transform: uppercase;
}

.plugin-status {
  font-size: 0.8em;
  padding: 2px 8px;
  border-radius: 12px;
  width: fit-content;
}

.plugin-status.running {
  background: #1a3a1a;
  color: #4caf50;
}

.plugin-status.stopped {
  background: #3a1a1a;
  color: #f44336;
}

.plugin-actions {
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
</style>
