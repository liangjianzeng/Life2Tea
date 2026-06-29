<template>
  <div v-if="modelValue" class="modal-overlay" @click.self="handleCancel">
    <div class="modal-content" :class="{ 'file-mode': allowFile }">
      <div class="modal-header">
        <h3>{{ getPathTypeTitle }}</h3>
        <button class="modal-close" @click="handleCancel">&times;</button>
      </div>
      <DirectoryBrowser
        :initial-path="initialPath"
        :allow-file="allowFile"
        :path-type="pathType"
        @select="handleSelect"
      />
      <div class="modal-footer">
        <button class="btn-cancel" @click="handleCancel">{{ t("settings.picker.cancel") }}</button>
        <button
          v-if="allowFile"
          class="btn-select"
          :disabled="!selectedFile"
          @click="handleSelect(selectedFile)"
        >
          {{ t("settings.picker.select") }}
        </button>
        <button
          v-else
          class="btn-select"
          :disabled="!currentPath"
          @click="handleSelect(currentPath)"
        >
          {{ t("settings.picker.select") }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { useI18n } from "vue-i18n";
import DirectoryBrowser from "./DirectoryBrowser.vue";

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  title: string;
  initialPath: string;
  allowFile: boolean;
  pathType: 'directory' | 'executable';
}>();

const getPathTypeTitle = computed(() => {
  if (props.pathType === 'executable') {
    return t('settings.picker.titleExe');
  }
  // Check if this is the backend directory
  if (props.initialPath && (props.initialPath.includes('llama') || props.initialPath.includes('backend'))) {
    return t('settings.picker.titleBackend');
  }
  return t('settings.picker.titleDir');
});

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "select", path: string): void;
}>();

const selectedFile = ref("");
const currentPath = ref("");

watch(() => props.modelValue, (val) => {
  if (val) {
    selectedFile.value = "";
  }
});

function handleSelect(path: string) {
  selectedFile.value = path;
  emit("select", path);
  emit("update:modelValue", false);
}

function handleCancel() {
  emit("update:modelValue", false);
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: #1a1a2e;
  border: 1px solid #534ab7;
  border-radius: 12px;
  width: 700px;
  max-width: 90%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #2d2d4a;
}

.modal-header h3 {
  margin: 0;
  color: #7c5cff;
  font-size: 1.1em;
}

.modal-close {
  background: none;
  border: none;
  color: #888;
  font-size: 1.5em;
  cursor: pointer;
  line-height: 1;
  padding: 0 4px;
}

.modal-close:hover {
  color: #e0e0ff;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid #2d2d4a;
}

.btn-cancel {
  padding: 8px 16px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9em;
}

.btn-cancel:hover {
  background: #3d3d5a;
}

.btn-select {
  padding: 8px 16px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9em;
}

.btn-select:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-select:hover:not(:disabled) {
  background: #6b5cc4;
}
</style>
