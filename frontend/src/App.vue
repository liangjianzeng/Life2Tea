<template>
  <div id="app">
    <header class="app-header">
      <h1>{{ t("app.title") }} <span class="version">{{ t("app.version") }}</span></h1>
      <nav>
        <router-link to="/">{{ t("app.nav.chat") }}</router-link>
        <router-link to="/models">{{ t("app.nav.models") }}</router-link>
        <router-link to="/plugins">{{ t("app.nav.plugins") }}</router-link>
        <router-link to="/settings">{{ t("app.nav.settings") }}</router-link>
        <router-link to="/api-keys">{{ t("app.nav.apiKeys") }}</router-link>
      </nav>
      <button class="lang-btn" @click="toggle">{{ locale === 'zh-CN' ? 'EN' : '中文' }}</button>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { toggleLocale } from "./i18n";

const { t, locale } = useI18n();

function toggle() {
  toggleLocale();
}
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
.lang-btn {
  margin-left: 16px;
  padding: 4px 12px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}
.lang-btn:hover {
  background: #3d3d5a;
}
</style>
