<template>
  <div class="dir-browser">
    <!-- Breadcrumb -->
    <div class="breadcrumb">
      <button class="breadcrumb-btn" @click="navigateTo('..')" :disabled="!canGoUp">
        <span class="icon">↑</span> 上一级
      </button>
      <span class="breadcrumb-sep">/</span>
      <div class="breadcrumb-path" ref="breadcrumbRef">
        <template v-for="(seg, i) in pathSegments" :key="i">
          <button
            v-if="i < pathSegments.length - 1"
            class="breadcrumb-link"
            @click="navigateToPath(i)"
          >
            {{ seg }}
          </button>
          <span v-else class="breadcrumb-current">{{ seg }}</span>
        </template>
      </div>
    </div>

    <!-- Content area -->
    <div class="content">
      <div class="path-hint">{{ getPathHint }}</div>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="error" class="error">{{ error }}</div>
      <div v-else-if="!dirs.length && !files.length" class="empty">{{ t("settings.picker.empty") }}</div>
      <div v-else class="grid">
        <!-- Directories -->
        <div
          v-for="dir in dirs"
          :key="'d-' + dir"
          class="item dir-item"
          @click="openDir(dir)"
        >
          <span class="icon folder">📁</span>
          <span class="name">{{ dir }}</span>
        </div>

        <!-- Files (only if allowFile) -->
        <div
          v-if="allowFile"
          v-for="file in files"
          :key="'f-' + file"
          class="item file-item"
          @click="selectFile(file)"
        >
          <span class="icon" :class="getFileClass(file)"></span>
          <span class="name">{{ file }}</span>
          <span v-if="isExecutable(file)" class="badge exe-badge">可执行</span>
          <span v-else-if="isModelFile(file)" class="badge model-badge">模型</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  initialPath?: string;
  allowFile?: boolean;
  pathType?: 'directory' | 'executable';
}>();

const { t } = useI18n();

const emit = defineEmits<{
  (e: "select", path: string): void;
  (e: "cancel"): void;
}>();

const currentPath = ref(props.initialPath || "");
const dirs = ref<string[]>([]);
const files = ref<string[]>([]);
const loading = ref(false);
const error = ref("");

const canGoUp = computed(() => currentPath.value && !isRoot(currentPath.value));

const pathSegments = computed(() => {
  if (!currentPath.value) return [];
  const p = currentPath.value.replace(/\\/g, "/");
  return p.split("/").filter(Boolean);
});

const getPathHint = computed(() => {
  if (props.pathType === 'executable') {
    return t('settings.picker.exeHint');
  }
  // Check if this is the backend directory
  if (props.initialPath && (props.initialPath.includes('llama') || props.initialPath.includes('backend'))) {
    return t('settings.picker.backendHint');
  }
  return t('settings.picker.modelHint');
});

const isRoot = (path: string) => {
  // Root check for Windows (e.g., "D:") and Linux (e.g., "/")
  if (/^[A-Za-z]:$/i.test(path)) return true;
  if (path === "/" || path === "") return true;
  return false;
};

async function loadDir(path: string) {
  loading.value = true;
  error.value = "";
  try {
    const res = await fetch(`/api/config/dirs/list?path=${encodeURIComponent(path)}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "加载目录失败");
    }
    const data = await res.json();
    dirs.value = data.dirs || [];
    files.value = data.files || [];
  } catch (e: any) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function openDir(name: string) {
  const next = currentPath.value
    ? currentPath.value.replace(/\\/g, "/") + "/" + name
    : name;
  // Normalize path separators
  currentPath.value = next.replace(/\/+/g, "/");
  loadDir(currentPath.value);
}

function navigateTo(action: string) {
  if (action === ".." && canGoUp.value) {
    const segs = pathSegments.value;
    if (segs.length <= 1) {
      currentPath.value = "";
    } else {
      // Reconstruct parent path
      const seg = segs[segs.length - 2];
      if (/^[A-Za-z]:$/i.test(seg)) {
        currentPath.value = seg;
      } else {
        currentPath.value = segs.slice(0, -1).join("/");
      }
    }
    loadDir(currentPath.value);
  }
}

function navigateToPath(index: number) {
  const segs = pathSegments.value;
  if (index < segs.length - 1) {
    const seg = segs[index + 1];
    if (/^[A-Za-z]:$/i.test(seg)) {
      currentPath.value = seg;
    } else {
      currentPath.value = segs.slice(0, index + 2).join("/");
    }
    loadDir(currentPath.value);
  }
}

function selectFile(name: string) {
  const fullPath = currentPath.value
    ? currentPath.value.replace(/\\/g, "/") + "/" + name
    : name;
  emit("select", fullPath.replace(/\/+/g, "/"));
}

function getFileClass(file: string): string {
  const ext = file.split(".").pop()?.toLowerCase();
  if (["exe", "sh", "bat", "cmd", "bin"].includes(ext || "")) return "exe";
  if (["gguf", "bin", "model"].includes(ext || "")) return "model";
  if (["json", "yaml", "yml", "toml", "cfg"].includes(ext || "")) return "config";
  return "file";
}

function isExecutable(file: string): boolean {
  const ext = file.split(".").pop()?.toLowerCase();
  if (["exe", "sh", "bat", "cmd", "bin"].includes(ext || "")) return true;
  // On Linux, no extension but exists could be executable
  if (!ext) return true;
  return false;
}

function isModelFile(file: string): boolean {
  const ext = file.split(".").pop()?.toLowerCase();
  if (["gguf", "bin", "model"].includes(ext || "")) return true;
  return false;
}

onMounted(() => {
  if (currentPath.value) {
    loadDir(currentPath.value);
  }
});
</script>

<style scoped>
.dir-browser {
  display: flex;
  flex-direction: column;
  height: 400px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #0d0d1a;
  border-bottom: 1px solid #2d2d4a;
  flex-wrap: wrap;
}

.breadcrumb-btn {
  padding: 2px 8px;
  background: #2d2d4a;
  color: #a0a0c0;
  border: 1px solid #3d3d5a;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8em;
  white-space: nowrap;
}

.breadcrumb-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.breadcrumb-btn:hover:not(:disabled) {
  background: #3d3d5a;
  color: #e0e0ff;
}

.breadcrumb-sep {
  color: #555;
  font-size: 0.85em;
}

.breadcrumb-path {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.breadcrumb-link {
  background: none;
  border: none;
  color: #7c5cff;
  cursor: pointer;
  font-size: 0.85em;
  padding: 2px 4px;
  border-radius: 3px;
  white-space: nowrap;
}

.breadcrumb-link:hover {
  background: rgba(124, 92, 255, 0.15);
}

.breadcrumb-current {
  color: #e0e0ff;
  font-size: 0.85em;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.path-hint {
  padding: 6px 12px;
  background: rgba(124, 92, 255, 0.1);
  border-bottom: 1px solid #2d2d4a;
  font-size: 0.8em;
  color: #a0a0c0;
  font-style: italic;
}

.loading,
.error {
  text-align: center;
  padding: 20px;
  color: #888;
}

.error {
  color: #f44336;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 6px;
}

.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}

.item:hover {
  background: rgba(124, 92, 255, 0.1);
  border-color: #534ab7;
}

.dir-item:hover {
  background: rgba(124, 92, 255, 0.1);
}

.icon {
  font-size: 1.2em;
  flex-shrink: 0;
}

.icon.folder {
  filter: hue-rotate(200deg);
}

.icon.exe {
  filter: hue-rotate(120deg);
}

.icon.model {
  filter: hue-rotate(280deg);
}

.icon.config {
  filter: hue-rotate(50deg);
}

.name {
  flex: 1;
  font-size: 0.85em;
  color: #d0d0e8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  font-size: 0.7em;
  padding: 1px 6px;
  background: #534ab7;
  color: #fff;
  border-radius: 3px;
  flex-shrink: 0;
}

.exe-badge {
  background: #4caf50;
}

.model-badge {
  background: #ff9800;
}
</style>
