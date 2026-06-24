<template>
  <div class="chat-view">
    <h2>Chat</h2>
    <p class="hint">Model loading and chat UI coming soon.</p>
    <div class="status" v-if="health">
      Backend: {{ health.status }} · Version: {{ health.version }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

const health = ref<{ status: string; version: string } | null>(null);

onMounted(async () => {
  try {
    const res = await fetch("/api/health");
    health.value = await res.json();
  } catch {}
});
</script>

<style scoped>
.chat-view { padding: 24px; color: #e0e0ff; }
.hint { opacity: 0.6; margin: 12px 0; }
.status { font-size: 0.85em; opacity: 0.5; }
</style>
