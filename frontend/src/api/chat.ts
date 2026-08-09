/**
 * Chat API client.
 */
import { api } from "./client";
import type { ChatMessage, ChatCompletionRequest, Conversation, ConversationDetail } from "../types";

export async function listConversations(): Promise<Conversation[]> {
  const data = await api.get<{ conversations: Conversation[] }>("/api/chat/conversations");
  return data.conversations || [];
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  return await api.get<ConversationDetail>(`/api/chat/conversation/${id}`);
}

export async function createConversation(title: string, model_family?: string): Promise<Conversation> {
  const data = await api.post<{ conversation: Conversation }>("/api/chat/conversation", {
    title,
    model_family: model_family || null,
  });
  return data.conversation;
}

export async function updateConversation(id: string, body: { title?: string; model_family?: string | null }):
  Promise<{ ok: boolean }> {
  return await api.put<{ ok: boolean }>(`/api/chat/conversation/${id}`, body);
}

export async function deleteConversation(id: string): Promise<{ ok: boolean }> {
  return await api.delete<{ ok: boolean }>(`/api/chat/conversation/${id}`);
}

export async function saveMessage(conversation_id: string, role: string, content: string): Promise<void> {
  await api.post<{ ok: boolean }>("/api/chat/message", { conversation_id, role, content });
}

export interface ChatStreamOptions {
  onDelta: (content: string) => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

/**
 * Robust streaming chat — consumes SSE via fetch reader, handles keep-alive
 * comments, error chunks and [DONE] termination.
 */
export async function streamChat(
  req: ChatCompletionRequest,
  opts: ChatStreamOptions,
): Promise<void> {
  const response = await fetch("/api/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, stream: true }),
    credentials: "include",
    signal: opts.signal,
  });

  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = body.detail || body.error?.message || JSON.stringify(body);
    } catch {
      detail = await response.text();
    }
    opts.onError(detail || `HTTP ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    opts.onError("Stream unavailable");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;

  try {
    while (true) {
      const { done: rdone, value } = await reader.read();
      if (rdone) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith(":")) continue; // keep-alive comment
        if (!trimmed.startsWith("data: ")) continue;
        const data = trimmed.slice(6);
        if (data === "[DONE]") { done = true; break; }
        try {
          const json = JSON.parse(data);
          if (json.error) {
            opts.onError(json.error.message || JSON.stringify(json.error));
            return;
          }
          const content = json.choices?.[0]?.delta?.content || "";
          if (content) opts.onDelta(content);
        } catch {
          /* partial frame — ignore */
        }
      }
      if (done) break;
    }
  } catch (e: any) {
    if (e.name !== "AbortError") opts.onError(e.message || "Stream error");
  }
}
