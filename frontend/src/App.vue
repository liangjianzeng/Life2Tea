<template>
  <div id="app">
    <header class="app-header">
      <h1>Life2Tea <span class="version">v0.1.0</span></h1>
      <nav>
        <router-link to="/">Chat</router-link>
        <router-link to="/models">Models</router-link>
        <router-link to="/plugins">Plugins</router-link>
        <router-link to="/settings">Settings</router-link>
      </nav>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";

const health = ref<{ status: string; version: string } | null>(null);

onMounted(async () => {
  try {
    const res = await fetch("/api/health");
    health.value = await res.json();
  } catch (e) {
    health.value = { status: "unreachable", version: "unknown" };
  }
});
</script>

<style>
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  background: #1a1a2e;
  color: #e0e0ff;
  border-bottom: 1px solid #2d2d4a;
}
.app-header nav a {
  color: #a0a0c0;
  text-decoration: none;
  margin-left: 16px;
}
.app-header nav a.router-link-active {
  color: #7c5cff;
}
.app-main {
  height: calc(100vh - 56px);
  background: #0f0f1a;
  color: #e0e0ff;
}
.version {
  font-size: 0.6em;
  opacity: 0.6;
}
</style>
