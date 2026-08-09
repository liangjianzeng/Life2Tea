/**
 * Gateway store — shared state for model endpoints/providers.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import { listModels, scanModels, loadModel, unloadModel } from "../api/models";
import type { ModelEndpoint } from "../types";

export const useGatewayStore = defineStore("gateway", () => {
  const providers = ref<ModelEndpoint[]>([]);
  const loading = ref(false);
  const error = ref("");

  async function refresh() {
    loading.value = true;
    error.value = "";
    try {
      providers.value = await listModels();
    } catch (e: any) {
      error.value = e.message || "Failed to load providers";
    } finally {
      loading.value = false;
    }
  }

  async function rescan() {
    loading.value = true;
    try {
      providers.value = await scanModels();
    } catch (e: any) {
      error.value = e.message || "Failed to rescan";
    } finally {
      loading.value = false;
    }
  }

  async function start(name: string) {
    const instance = await loadModel(name);
    const idx = providers.value.findIndex((p) => p.family === name);
    if (idx >= 0) providers.value[idx] = instance;
    return instance;
  }

  async function stop(name: string) {
    const instance = await unloadModel(name);
    const idx = providers.value.findIndex((p) => p.family === name);
    if (idx >= 0) providers.value[idx] = instance;
    return instance;
  }

  return { providers, loading, error, refresh, rescan, start, stop };
});
