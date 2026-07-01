<template>
  <div class="chat-view">
    <!-- Sidebar -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <h3>{{ t("chat.conversations") }}</h3>
        <button class="btn-new-convo" @click="createNewConversation" title="New conversation">+</button>
      </div>

      <div v-if="conversations.length === 0" class="sidebar-empty">{{ t("chat.noConversations") }}</div>

      <ul class="conversation-list">
        <li v-for="conv in conversations" :key="conv.id"
            :class="['conv-item', { active: conv.id === conversationId }]"
            @click="switchConversation(conv)">
          <div class="conv-info">
            <span class="conv-title">{{ conv.title || t("chat.untitled") }}</span>
            <span class="conv-time">{{ formatTime(conv.updated_at) }}</span>
          </div>
          <button class="btn-delete-conv" @click.stop="deleteConversation(conv.id)" title="Delete conversation">×</button>
        </li>
      </ul>

      <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed">
        {{ sidebarCollapsed ? '→' : '←' }}
      </button>
    </aside>

    <!-- Main chat area -->
    <div class="chat-main">
      <div class="chat-header">
        <button class="btn-sidebar-open" @click="toggleSidebar" title="Toggle conversations">☰</button>
        <h2>{{ t("chat.title") }}</h2>
        <span class="model-badge" v-if="selectedModel">{{ selectedModel }}</span>
      </div>

      <!-- Fixed-height scrollable messages area -->
      <div class="messages" ref="messagesContainer">
        <div v-for="(msg, idx) in messages" :key="idx"
             :class="['message', msg.role]">
          <div class="role">{{ msg.role === 'user' ? t('chat.you') : t('chat.ai') }}</div>
          <div class="content">{{ msg.content }}</div>
        </div>
        <div v-if="loading" class="message assistant">
          <div class="role">{{ t("chat.ai") }}</div>
          <div class="content">{{ streamingContent }}<span class="cursor">|</span></div>
        </div>
      </div>

      <form class="chat-input" @submit.prevent="sendMessage">
        <textarea
          v-model="inputMessage"
          :placeholder="t('chat.placeholder')"
          @keydown="handleKeydown"
          :disabled="loading"
          rows="1"
          ref="inputRef"
        ></textarea>
        <button type="submit" :disabled="loading || !inputMessage.trim()">
          {{ loading ? t('chat.sending') : t('chat.send') }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

const messages = ref<{ role: string; content: string }[]>([]);
const inputMessage = ref("");
const loading = ref(false);
const streamingContent = ref("");
const selectedModel = ref<string | null>(null);
const allModels = ref<any[]>([]);
const conversations = ref<any[]>([]);
const messagesContainer = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLTextAreaElement | null>(null);
let conversationId: string | null = null;
const sidebarCollapsed = ref(false);

async function loadModels() {
  try {
    const response = await fetch("/api/models", { credentials: "include" });
    if (response.ok) {
      const data = await response.json();
      allModels.value = data.models || [];
      for (const m of allModels.value) {
        if (m.instance && m.instance.status === "running") {
          selectedModel.value = m.display;
          break;
        }
      }
    }
  } catch (e) { /* silent */ }
}

async function loadConversations() {
  try {
    const response = await fetch("/api/chat/conversations", { credentials: "include" });
    if (response.ok) {
      const data = await response.json();
      conversations.value = data.conversations || [];
    }
  } catch (e) { /* silent */ }
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  // Toggle backdrop class for mobile
  document.querySelector('.chat-view')?.classList.toggle('sidebar-open', !sidebarCollapsed.value);
}

async function switchConversation(conv: any) {
  conversationId = conv.id;
  messages.value = [];
  selectedModel.value = null;
  try {
    const response = await fetch(`/api/chat/conversation/${conv.id}`, { credentials: "include" });
    if (response.ok) {
      const data = await response.json();
      messages.value = data.messages.map((m: any) => ({ role: m.role, content: m.content }));
      if (conv.model_family && allModels.value.length > 0) {
        for (const m of allModels.value) {
          if (m.family === conv.model_family && m.instance?.status === "running") {
            selectedModel.value = m.display;
            break;
          }
        }
      }
    }
  } catch (e) { /* silent */ }
  await nextTick();
  scrollToBottom();
}

async function createNewConversation() {
  const title = t("chat.newConversation");
  try {
    const response = await fetch("/api/chat/conversation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, model_family: selectedModel.value || undefined }),
      credentials: "include",
    });
    if (response.ok) {
      const data = await response.json();
      conversationId = data.conversation.id;
      messages.value = [];
      streamingContent.value = "";
      inputMessage.value = "";
      loading.value = false;
      await loadConversations();
      inputRef.value?.focus();
    }
  } catch (e) { /* silent */ }
}

async function deleteConversation(id: string) {
  if (!confirm(t("chat.confirmDelete"))) return;
  try {
    const response = await fetch(`/api/chat/conversation/${id}`, { method: "DELETE", credentials: "include" });
    if (response.ok) {
      if (conversationId === id) {
        conversationId = null;
        messages.value = [];
        await createNewConversation();
      }
      await loadConversations();
    }
  } catch (e) { /* silent */ }
}

function formatTime(ts: number): string {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffMins = Math.floor((now.getTime() - d.getTime()) / 60000);
  if (diffMins < 1) return t("chat.justNow");
  if (diffMins < 60) return `${diffMins}m`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d`;
  return d.toLocaleDateString();
}

async function saveMessage(role: string, content: string) {
  if (!conversationId) {
    const createResponse = await fetch("/api/chat/conversation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: content.substring(0, 50), model_family: selectedModel.value || undefined }),
      credentials: "include",
    });
    if (createResponse.ok) {
      const data = await createResponse.json();
      conversationId = data.conversation.id;
      await loadConversations();
    }
  }
  if (conversationId) {
    await fetch("/api/chat/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, role, content }),
      credentials: "include",
    });
  }
}

async function sendMessage() {
  const text = inputMessage.value.trim();
  if (!text || loading.value) return;

  messages.value.push({ role: "user", content: text });
  inputMessage.value = "";
  loading.value = true;
  streamingContent.value = "";

  await saveMessage("user", text);
  await nextTick();
  scrollToBottom();

  try {
    const response = await fetch("/api/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: messages.value.map(m => ({ role: m.role, content: m.content })),
        stream: true, max_tokens: 2048,
      }),
      credentials: "include",
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (data === "[DONE]") break;
            try {
              const json = JSON.parse(data);
              const content = json.choices?.[0]?.delta?.content || "";
              streamingContent.value += content;
              await nextTick();
              scrollToBottom();
            } catch (e) { /* ignore */ }
          }
        }
      }
    }

    messages.value.push({ role: "assistant", content: streamingContent.value });
    streamingContent.value = "";
    await saveMessage("assistant", messages.value[messages.value.length - 1].content);
  } catch (error: any) {
    const errMsg = error.message || t("chat.error", { msg: "Failed to send message" });
    messages.value.push({ role: "assistant", content: t("chat.error", { msg: errMsg }) });
    await saveMessage("assistant", messages.value[messages.value.length - 1].content);
  } finally {
    loading.value = false;
    await nextTick();
    scrollToBottom();
    inputRef.value?.focus();
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

let isUserScrolledUp = false;
function handleScroll() {
  const el = messagesContainer.value;
  if (!el) return;
  const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  isUserScrolledUp = distFromBottom > 100;
}

function scrollToBottom() {
  const el = messagesContainer.value;
  if (!el || isUserScrolledUp) return;
  el.scrollTop = el.scrollHeight;
}

onMounted(async () => {
  inputRef.value?.focus();
  await loadModels();
  await loadConversations();
  try {
    const response = await fetch("/api/chat/conversations", { credentials: "include" });
    if (response.ok) {
      const data = await response.json();
      if (data.conversations && data.conversations.length > 0) {
        const latestConv = data.conversations[0];
        conversationId = latestConv.id;
        if (latestConv.model_family) {
          for (const m of allModels.value) {
            if (m.family === latestConv.model_family && m.instance?.status === "running") {
              selectedModel.value = m.display;
              break;
            }
          }
        }
        const convResponse = await fetch(`/api/chat/conversation/${conversationId}`, { credentials: "include" });
        if (convResponse.ok) {
          const convData = await convResponse.json();
          messages.value = convData.messages.map((m: any) => ({ role: m.role, content: m.content }));
        }
      } else {
        await createNewConversation();
      }
    }
  } catch (e) {
    await createNewConversation();
  }
  messagesContainer.value?.addEventListener("scroll", handleScroll);
});
</script>

<style scoped>
/* Layout */
.chat-view {
  display: flex;
  height: 100%;
  overflow: hidden;
  position: relative;
}

/* Sidebar - overlay on mobile, fixed on desktop */
.sidebar {
  width: 260px;
  min-width: 260px;
  background: #1a1a2e;
  border-right: 1px solid #2d2d4a;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.3s ease, opacity 0.3s ease;
  z-index: 100;
}

.sidebar.collapsed {
  transform: translateX(-100%);
  opacity: 0;
  pointer-events: none;
}

/* Mobile: sidebar is overlay */
@media (max-width: 768px) {
  .sidebar {
    position: absolute;
    top: 0;
    left: 0;
    bottom: 0;
    width: 280px;
    min-width: 280px;
    box-shadow: 4px 0 16px rgba(0, 0, 0, 0.5);
  }

  .sidebar.collapsed {
    transform: translateX(-100%);
  }

  /* Overlay backdrop */
  .chat-view::before {
    content: '';
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease;
    z-index: 99;
  }

  .chat-view:not(.sidebar-collapsed)::before {
    opacity: 1;
    pointer-events: auto;
  }
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #2d2d4a;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 1em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.btn-new-convo {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: #534ab7;
  color: #fff;
  font-size: 1.2em;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.btn-new-convo:hover { background: #6b5cc4; }

.sidebar-empty {
  padding: 24px 16px;
  color: #888;
  font-size: 0.9em;
  text-align: center;
}

.conversation-list {
  list-style: none;
  margin: 0;
  padding: 8px 0;
  flex: 1;
  overflow-y: auto;
}

.conv-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}

.conv-item:hover { background: #252545; }

.conv-item.active {
  background: #2d2d5a;
  border-left-color: #534ab7;
}

.conv-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv-title {
  font-size: 0.9em;
  color: #e0e0ff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-time {
  font-size: 0.75em;
  color: #888;
}

.btn-delete-conv {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: #888;
  font-size: 1.1em;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
  flex-shrink: 0;
}

.conv-item:hover .btn-delete-conv { opacity: 1; }

.btn-delete-conv:hover {
  background: #c0392b;
  color: #fff;
}

.sidebar-toggle {
  position: absolute;
  right: -14px;
  top: 50%;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid #2d2d4a;
  background: #1a1a2e;
  color: #aaa;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8em;
  z-index: 5;
}

.sidebar-toggle:hover { background: #2d2d4a; color: #fff; }

/* Main chat area */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid #2d2d4a;
  flex-shrink: 0;
}

.chat-header h2 { margin: 0; font-size: 1.2em; }

/* Sidebar toggle button in chat header (mobile only) */
.btn-sidebar-open {
  display: none;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  border: 1px solid #2d2d4a;
  background: transparent;
  color: #e0e0ff;
  font-size: 1.2em;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.btn-sidebar-open:hover {
  background: #2d2d4a;
}

.model-badge {
  font-size: 0.8em;
  background: #534ab7;
  color: #fff;
  padding: 2px 8px;
  border-radius: 12px;
}

/* Fixed-height scrollable messages */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0; /* Critical for flex child scrolling */
}

.message {
  padding: 10px 14px;
  border-radius: 8px;
  max-width: 85%;
}

.message.user {
  align-self: flex-end;
  background: #534ab7;
  color: #fff;
}

.message.assistant {
  align-self: flex-start;
  background: #1a1a2e;
  color: #e0e0ff;
  border: 1px solid #2d2d4a;
}

.role {
  font-size: 0.75em;
  opacity: 0.6;
  margin-bottom: 4px;
  font-weight: 600;
}

.content {
  white-space: pre-wrap;
  word-break: break-word;
}

.cursor { animation: blink 1s infinite; }

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid #2d2d4a;
  flex-shrink: 0;
}

.chat-input textarea {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #2d2d4a;
  border-radius: 8px;
  background: #1a1a2e;
  color: #e0e0ff;
  font-family: inherit;
  font-size: 0.95em;
  resize: none;
  outline: none;
  min-height: 40px;
  max-height: 120px;
}

.chat-input textarea:focus { border-color: #534ab7; }

.chat-input button {
  padding: 10px 20px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.95em;
  white-space: nowrap;
}

.chat-input button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chat-input button:hover:not(:disabled) { background: #6b5cc4; }

/* ===== Mobile Responsive (≤768px) ===== */
@media (max-width: 768px) {
  .chat-view {
    position: relative;
  }

  /* Sidebar becomes overlay on mobile, below the header */
  .sidebar {
    position: fixed;
    top: 52px;
    left: 0;
    bottom: 0;
    width: 280px;
    min-width: 280px;
    z-index: 1000;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    box-shadow: none;
  }

  .sidebar:not(.collapsed) {
    transform: translateX(0);
  }

  /* Backdrop overlay - below header */
  .chat-view::before {
    content: '';
    position: fixed;
    top: 52px;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease;
    z-index: 998;
  }

  .chat-view.sidebar-open::before {
    opacity: 1;
    pointer-events: auto;
  }

  /* Mobile sidebar header */
  .sidebar-header {
    padding: 12px 16px;
  }

  .sidebar-header h3 {
    font-size: 0.95em;
  }

  /* Conversation list items smaller on mobile */
  .conv-item {
    padding: 8px 12px;
  }

  .conv-title {
    font-size: 0.85em;
  }

  .btn-delete-conv {
    width: 28px;
    height: 28px;
    opacity: 1; /* Always visible on mobile */
  }

  /* Chat header adapts to full width */
  .chat-header {
    padding: 12px 16px;
    gap: 8px;
    height: 52px;
    flex-shrink: 0;
  }

  .chat-header h2 {
    font-size: 1em;
  }

  /* Messages area uses full width on mobile */
  .messages {
    padding: 12px 16px;
    gap: 8px;
  }

  .message {
    max-width: 90%;
    padding: 8px 12px;
  }

  /* Input area adapts to mobile */
  .chat-input {
    padding: 12px 16px;
    gap: 6px;
  }

  .chat-input textarea {
    font-size: 0.9em;
    min-height: 36px;
    padding: 8px 12px;
  }

  .chat-input button {
    padding: 8px 14px;
    font-size: 0.9em;
  }

  /* Sidebar toggle moves to chat header on mobile */
  .sidebar-toggle {
    display: none;
  }

  /* Mobile-only sidebar trigger in chat header */
  .chat-header .btn-sidebar-open {
    display: flex !important;
  }
}

/* Extra small screens (≤480px) */
@media (max-width: 480px) {
  .sidebar {
    width: 100%;
    min-width: 100%;
  }

  .chat-header h2 {
    font-size: 0.95em;
  }

  .messages {
    padding: 8px 12px;
  }

  .message {
    max-width: 95%;
    padding: 6px 10px;
    font-size: 0.9em;
  }

  .chat-input {
    padding: 8px 12px;
  }

  .chat-input textarea {
    min-height: 32px;
    padding: 6px 10px;
  }

  .model-badge {
    font-size: 0.7em;
    padding: 1px 6px;
  }
}
</style>
