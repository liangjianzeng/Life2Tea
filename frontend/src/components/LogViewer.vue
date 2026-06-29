<template>
  <div class="log-viewer">
    <div class="log-controls">
      <select v-model="filterLevel" class="level-filter">
        <option value="">{{ t("logs.allLevels") }}</option>
        <option value="INFO">{{ t("logs.info") }}</option>
        <option value="WARNING">{{ t("logs.warning") }}</option>
        <option value="ERROR">{{ t("logs.error") }}</option>
        <option value="DEBUG">{{ t("logs.debug") }}</option>
      </select>
      <input v-model="searchQuery" :placeholder="t('logs.search')" class="log-search" />
    </div>
    <div class="log-entries">
      <div v-for="(log, idx) in filteredLogs" :key="idx"
           class="log-entry" :class="'level-' + log.level">
        <span class="log-time">{{ formatTime(log.timestamp) }}</span>
        <span class="log-level">{{ log.level }}</span>
        <span class="log-module">{{ log.module }}</span>
        <span class="log-message">{{ log.message }}</span>
      </div>
      <div v-if="filteredLogs.length === 0" class="empty">
        {{ t("logs.noLogs") }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const props = defineProps<{
  logs: any[];
}>();

const filterLevel = ref("");
const searchQuery = ref("");

const filteredLogs = computed(() => {
  let result = props.logs;
  if (filterLevel.value) {
    result = result.filter((l: any) => l.level === filterLevel.value);
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    result = result.filter((l: any) =>
      (l.message || "").toLowerCase().includes(q) ||
      (l.module || "").toLowerCase().includes(q)
    );
  }
  return result;
});

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return ts;
  }
}
</script>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-controls {
  display: flex;
  gap: 8px;
}

.level-filter,
.log-search {
  padding: 4px 8px;
  background: #0f0f1a;
  color: #e0e0ff;
  border: 1px solid #2d2d4a;
  border-radius: 4px;
  font-size: 0.8em;
}

.level-filter:focus,
.log-search:focus {
  outline: none;
  border-color: #534ab7;
}

.log-search {
  flex: 1;
}

.log-entries {
  max-height: 200px;
  overflow-y: auto;
  font-family: 'Fira Code', monospace;
  font-size: 0.78em;
}

.log-entry {
  display: flex;
  gap: 10px;
  padding: 4px 8px;
  border-bottom: 1px solid #1a1a2e;
  align-items: center;
}

.log-entry:hover {
  background: #1a1a2e;
}

.log-time { color: #666; flex-shrink: 0; }
.log-level { flex-shrink: 0; font-weight: 600; min-width: 56px; }
.log-module { color: #818cf8; flex-shrink: 0; min-width: 80px; }

.level-INFO { color: #60a5fa; }
.level-WARNING { color: #fbbf24; }
.level-ERROR { color: #f87171; }
.level-DEBUG { color: #888; }

.log-message {
  color: #c0c0e0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty {
  text-align: center;
  color: #666;
  padding: 20px;
}
</style>
