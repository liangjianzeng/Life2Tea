<template>
  <div class="settings-view">
    <h2>Settings</h2>
    <div class="form-group">
      <label>Models Directory</label>
      <input v-model="config.models_dir" />
    </div>
    <div class="form-group">
      <label>llama.cpp Backend Dir</label>
      <input v-model="config.llama_backend_dir" />
    </div>
    <div class="form-group">
      <label>Backend Preference</label>
      <select v-model="config.backend_preference">
        <option value="auto">Auto</option>
        <option value="cuda">CUDA</option>
        <option value="vulkan">Vulkan</option>
        <option value="sycl">SYCL</option>
      </select>
    </div>
    <button @click="save">Save</button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

const config = ref<any>({});

onMounted(async () => {
  try {
    const res = await fetch("/api/config/global");
    config.value = await res.json();
  } catch {}
});

async function save() {
  await fetch("/api/config/global", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config.value),
  });
  alert("Saved!");
}
</script>

<style scoped>
.settings-view { padding: 24px; color: #e0e0ff; }
.form-group { margin: 12px 0; }
.form-group label { display: block; margin-bottom: 4px; opacity: 0.7; font-size: 0.9em; }
.form-group input, .form-group select {
  width: 400px; padding: 6px 10px; background: #1a1a2e; color: #e0e0ff;
  border: 1px solid #333; border-radius: 4px;
}
button { margin-top: 12px; padding: 6px 16px; background: #534ab7; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
</style>
