<template>
  <div class="model-router-status">
    <div class="header">
      <h3>模型路由状态</h3>
      <div class="stats">
        <span class="stat-item">
          <span class="label">运行实例</span>
          <span class="value">{{ instanceCount }}</span>
        </span>
        <span class="stat-item">
          <span class="label">常用模型</span>
          <span class="value">{{ commonModels.length }}</span>
        </span>
      </div>
    </div>

    <div v-if="instances.length === 0" class="empty-state">
      <p>暂无运行中的模型实例</p>
      <p class="hint">加载模型后将自动显示在这里</p>
    </div>

    <div v-else class="instances-list">
      <div
        v-for="inst in instances"
        :key="inst.family"
        class="instance-card"
      >
        <div class="instance-info">
          <div class="family-name">{{ getInstanceDisplay(inst.family) }}</div>
          <div class="port-info">端口: {{ inst.port }}</div>
        </div>
        <div class="instance-status" :class="inst.status">
          {{ inst.status === 'running' ? '运行中' : '未知' }}
        </div>
        <div class="instance-details">
          <div class="detail-item">
            <span class="label">最后使用</span>
            <span class="value">{{ formatTime(inst.lastUsed) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";

interface Instance {
  family: string;
  port: number;
  host: string;
  status: string;
  lastUsed: number;
}

const { t } = useI18n();

const instances = ref<Instance[]>([]);
const commonModels = ref<string[]>([]);
const instanceCount = ref(0);
const loading = ref(false);

const modelFamilyDisplay: Record<string, string> = {
  "qwen3.6": "Qwen3.6-35B-A3B",
  "glm": "GLM-4.7-Flash",
  "lfm2": "LFM2-24B",
};

function getInstanceDisplay(family: string): string {
  return modelFamilyDisplay[family] || family;
}

function formatTime(timestamp: number): string {
  if (!timestamp) return "-";
  const date = new Date(timestamp * 1000);
  return date.toLocaleString();
}

async function loadStatus() {
  loading.value = true;
  try {
    const [statusRes, commonRes] = await Promise.all([
      fetch("/api/model-router/status", { credentials: "include" }),
      fetch("/api/model-router/common-models", { credentials: "include" }),
    ]);

    const statusData = await statusRes.json();
    const commonData = await commonRes.json();

    instances.value = statusData.instances || [];
    commonModels.value = commonData.models || [];
    instanceCount.value = statusData.instance_count || 0;
  } catch (e) {
    console.error("Failed to load router status:", e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadStatus();
});

onUnmounted(() => {
  // Cleanup if needed
});
</script>

<style scoped>
.model-router-status {
  background: #1a1a2e;
  border: 1px solid #2d2d4a;
  border-radius: 12px;
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.header h3 {
  margin: 0;
  color: #e0e0ff;
  font-size: 1.1em;
}

.stats {
  display: flex;
  gap: 20px;
}

.stat-item {
  display: flex;
  gap: 6px;
  font-size: 0.9em;
}

.stat-item .label {
  color: #888;
}

.stat-item .value {
  color: #e0e0ff;
  font-weight: 600;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #888;
}

.empty-state .hint {
  margin-top: 8px;
  font-size: 0.9em;
  color: #666;
}

.instances-list {
  display: grid;
  gap: 12px;
}

.instance-card {
  background: #0f0f1a;
  border: 1px solid #2d2d4a;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.instance-info {
  flex: 1;
  min-width: 150px;
}

.family-name {
  font-size: 1em;
  font-weight: 600;
  color: #e0e0ff;
}

.port-info {
  font-size: 0.85em;
  color: #888;
  margin-top: 4px;
}

.instance-status {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.85em;
  font-weight: 600;
}

.instance-status.running {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
}

.instance-status.stopped {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

.instance-details {
  flex: 1;
  min-width: 150px;
  font-size: 0.85em;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.detail-item .label {
  color: #888;
}

.detail-item .value {
  color: #a0a0c0;
  font-family: 'Fira Code', monospace;
}
</style>
