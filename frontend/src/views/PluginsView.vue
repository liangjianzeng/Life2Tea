<template>
  <div class="plugins-view">
    <h2>Plugins</h2>
    <div v-if="plugins.length">
      <div v-for="p in plugins" :key="p.family" class="plugin-card">
        <strong>{{ p.display }}</strong>
        <span class="badge" :class="{ running: p.instance }">{{ p.instance ? 'running' : 'stopped' }}</span>
      </div>
    </div>
    <p v-else class="hint">No plugins loaded.</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

const plugins = ref<any[]>([]);

onMounted(async () => {
  try {
    const res = await fetch("/api/plugins");
    const data = await res.json();
    plugins.value = data.plugins || [];
  } catch {}
});
</script>

<style scoped>
.plugins-view { padding: 24px; color: #e0e0ff; }
.plugin-card { padding: 8px 12px; margin: 6px 0; background: #1a1a2e; border-radius: 6px; display: flex; gap: 12px; align-items: center; }
.badge { font-size: 0.75em; padding: 2px 8px; border-radius: 4px; background: #333; color: #aaa; }
.badge.running { background: #0f6e56; color: #fff; }
.hint { opacity: 0.6; }
</style>
