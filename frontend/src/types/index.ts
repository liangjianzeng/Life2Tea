/**
 * Shared TypeScript types for the Unified Model Gateway frontend.
 */

// ── Chat ───────────────────────────────────────────────────
export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatCompletionRequest {
  messages: ChatMessage[];
  model?: string;
  stream?: boolean;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
}

export interface Conversation {
  id: string;
  title: string;
  model_family?: string;
  created_at?: number;
  updated_at?: number;
  is_active?: boolean;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: ChatMessage[];
}

// ── Models / Providers ────────────────────────────────────
export type ProviderKind = "llamacpp" | "vllm" | "sglang";
export type EndpointStatus = "stopped" | "starting" | "running" | "error";

export interface ModelEndpoint {
  family: string;
  display: string;
  provider: ProviderKind;
  host: string;
  port: number;
  model_path: string;
  model_name: string;
  status: EndpointStatus;
  pid: number;
  params: Record<string, unknown>;
  instance?: {
    name: string;
    provider: ProviderKind;
    host: string;
    port: number;
    status: EndpointStatus;
    pid: number;
  } | null;
}

// ── Metrics / Dashboard ───────────────────────────────────
export interface ModelServerMetric {
  pid: number;
  port: number;
  model_name: string;
  tok_s: number;
  tok_s_peak: number;
  prompt_tok_s: number;
  prompt_tok_s_peak: number;
  total_prompt_tokens: number;
  total_predicted_tokens: number;
  kv_cache_used: number;
  kv_cache_total: number;
  rss: number;
  spec?: string;
  mtp?: number;
  source?: "metrics" | "probe";
  alive?: boolean;
}
