<template>
  <div class="models-view">
    <h2>Models</h2>
    <button @click="scan">Scan Models</button>
    <div v-if="models.length">
      <div v-for="m in models" :key="m.family" class="model-card">
        <strong>{{ m.display }}</strong>
        <span>{{ m.size_gb }} GB · {{ m.quantization }}</span>
      </div>
    </div>
    <p v-else class="hint">No models found. Configure models_dir in Settings.</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

const models = ref<any[]>([]);

async function scan() {
  const res = await fetch("/api/models/scan", { method: "POST" });
  const data = await res.json();
  models.value = data.models || [];
}

onMounted(scan);
</script>

<style scoped>
.models-view { padding: 24px; color: #e0e0ff; }
button { margin-bottom: 12px; padding: 6px 16px; background: #534ab7; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
.model-card { padding: 8px 12px; margin: 6px 0; background: #1a1a2e; border-radius: 6px; display: flex; gap: 12px; align-items: center; }
.hint { opacity: 0.6; }
</style>
