/**
 * Models / Providers API client.
 */
import { api } from "./client";
import type { ModelEndpoint } from "../types";

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
