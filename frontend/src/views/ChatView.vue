<template>
  <div class="chat-view">
    <div class="chat-header">
      <h2>{{ t("chat.title") }}</h2>
      <span class="model-badge" v-if="selectedModel">{{ selectedModel }}</span>
    </div>

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
const messagesContainer = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLTextAreaElement | null>(null);

async function sendMessage() {
  const text = inputMessage.value.trim();
  if (!text || loading.value) return;

  messages.value.push({ role: "user", content: text });
  inputMessage.value = "";
  loading.value = true;
  streamingContent.value = "";

  await nextTick();
  scrollToBottom();

  try {
    const response = await fetch("/api/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: messages.value.map(m => ({ role: m.role, content: m.content })),
        stream: true,
        max_tokens: 2048,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }

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
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }
    }

    messages.value.push({ role: "assistant", content: streamingContent.value });
    streamingContent.value = "";
  } catch (error: any) {
    messages.value.push({
      role: "assistant",
      content: t("chat.error", { msg: error.message || t("chat.error", { msg: "Failed to send message" }) }),
    });
  } finally {
    loading.value = false;
    await nextTick();
    scrollToBottom();
    inputRef.value?.focus();
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

onMounted(() => {
  inputRef.value?.focus();
});
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 800px;
  margin: 0 auto;
  padding: 0 16px;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
  border-bottom: 1px solid #2d2d4a;
}

.chat-header h2 {
  margin: 0;
  font-size: 1.2em;
}

.model-badge {
  font-size: 0.8em;
  background: #534ab7;
  color: #fff;
  padding: 2px 8px;
  border-radius: 12px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  padding: 10px 14px;
  border-radius: 8px;
  max-width: 80%;
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

.cursor {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 16px 0;
  border-top: 1px solid #2d2d4a;
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

.chat-input textarea:focus {
  border-color: #534ab7;
}

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

.chat-input button:hover:not(:disabled) {
  background: #6b5cc4;
}
</style>
