<template>
  <div id="app">
    <header class="app-header">
      <h1>{{ t("app.title") }} <span class="version">{{ t("app.version") }}</span></h1>
      <nav>
        <router-link to="/">{{ t("app.nav.chat") }}</router-link>
        <router-link to="/dashboard">{{ t("app.nav.dashboard") }}</router-link>
        <router-link to="/models">{{ t("app.nav.models") }}</router-link>
        <router-link to="/plugins">{{ t("app.nav.plugins") }}</router-link>
        <router-link to="/settings">{{ t("app.nav.settings") }}</router-link>
        <router-link to="/api-keys">{{ t("app.nav.apiKeys") }}</router-link>
        <router-link to="/logs">{{ t("app.nav.logs") }}</router-link>
      </nav>
      <div class="header-right">
        <span v-if="user" class="user-info">{{ user.email }}</span>
        <button v-if="user" class="logout-btn" @click="handleLogout">
          {{ t("auth.logout") }}
        </button>
        <button class="lang-btn" @click="toggle">{{ locale === 'zh-CN' ? 'EN' : '中文' }}</button>
      </div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { toggleLocale } from "./i18n";
import { checkAuth, logout as apiLogout } from "./services/auth";

const { t, locale } = useI18n();
const router = useRouter();

const user = ref<{ email: string } | null>(null);

onMounted(async () => {
  const auth = await checkAuth();
  if (auth.user) {
    user.value = auth.user;
  }
});

async function handleLogout() {
  await apiLogout();
  user.value = null;
  router.push("/login");
}

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
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.user-info {
  font-size: 0.85em;
  color: #888;
}
.logout-btn {
  padding: 4px 12px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
}
.logout-btn:hover {
  background: #3d3d5a;
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
