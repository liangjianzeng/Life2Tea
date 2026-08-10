/**
 * Models / Providers API client.
 */
import { api } from "./client";
import type { ModelEndpoint, ModelConfig, ProviderSchema } from "../types";

export async function listModels(): Promise<ModelEndpoint[]> {
  const data = await api.get<{ models: ModelEndpoint[] }>("/api/models");
  return data.models || [];
}

export async function scanModels(): Promise<ModelEndpoint[]> {
  const data = await api.post<{ models: ModelEndpoint[] }>("/api/models/scan", {});
  return data.models || [];
}

export async function loadModel(family: string): Promise<ModelEndpoint> {
  const data = await api.post<{ ok: boolean; instance: ModelEndpoint }>(
    `/api/models/${family}/load`, {},
  );
  return data.instance;
}

export async function unloadModel(family: string): Promise<ModelEndpoint> {
  const data = await api.post<{ ok: boolean; instance: ModelEndpoint }>(
    `/api/models/${family}/unload`, {},
  );
  return data.instance;
}

export async function getModelParams(family: string): Promise<Record<string, unknown>> {
  const data = await api.get<{ params: Record<string, unknown> }>(`/api/models/${family}/params`);
  return data.params;
}

export async function listBackends(): Promise<
  { kind: string; label: string; available: boolean; schema: ProviderSchema }[]
> {
  const data = await api.get<{ backends: { kind: string; label: string; available: boolean; schema: ProviderSchema }[] }>(
    "/api/models/backends",
  );
  return data.backends || [];
}

export async function createModel(family: string, config: ModelConfig): Promise<void> {
  await api.post<{ ok: boolean }>("/api/models", { family, ...config });
}

export async function updateModel(family: string, config: ModelConfig): Promise<void> {
  await api.put<{ ok: boolean }>(`/api/models/${family}`, config);
}

export async function deleteModel(family: string): Promise<void> {
  await api.delete<{ ok: boolean }>(`/api/models/${family}`);
}

export async function disableModel(family: string): Promise<void> {
  await api.post<{ ok: boolean }>(`/api/models/${family}/disable`, {});
}

export async function enableModel(family: string): Promise<void> {
  await api.post<{ ok: boolean }>(`/api/models/${family}/enable`, {});
}
