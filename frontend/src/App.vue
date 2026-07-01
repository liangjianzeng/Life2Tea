<template>
  <div id="app">
    <header class="app-header">
      <div class="header-left">
        <h1>{{ t("app.title") }} <span class="version">{{ t("app.version") }}</span></h1>
      </div>
      <nav class="top-nav">
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
        <button v-if="user" class="menu-toggle" @click="menuOpen = !menuOpen">
          {{ menuOpen ? '✕' : '☰' }}
        </button>
      </div>
    </header>
    <div v-if="user && menuOpen" class="mobile-menu" @click="menuOpen = false">
      <nav class="mobile-nav">
        <router-link to="/">{{ t("app.nav.chat") }}</router-link>
        <router-link to="/dashboard">{{ t("app.nav.dashboard") }}</router-link>
        <router-link to="/models">{{ t("app.nav.models") }}</router-link>
        <router-link to="/plugins">{{ t("app.nav.plugins") }}</router-link>
        <router-link to="/settings">{{ t("app.nav.settings") }}</router-link>
        <router-link to="/api-keys">{{ t("app.nav.apiKeys") }}</router-link>
        <router-link to="/logs">{{ t("app.nav.logs") }}</router-link>
      </nav>
    </div>
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
const menuOpen = ref(false);

onMounted(async () => {
  const auth = await checkAuth();
  if (auth.user) {
    user.value = auth.user;
  }
});

async function handleLogout() {
  await apiLogout();
  user.value = null;
  menuOpen.value = false;
  router.push("/login");
}

function toggle() {
  toggleLocale();
}
</script>

<style>
/* Global background fix */
body, html, #app {
  margin: 0;
  padding: 0;
  background: #0f0f1a;
  min-height: 100vh;
}
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
.header-left {
  display: flex;
  align-items: center;
}
.app-header .top-nav a {
  color: #a0a0c0;
  text-decoration: none;
  margin-left: 16px;
}
.app-header .top-nav a.router-link-active {
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
.menu-toggle {
  display: none;
  padding: 4px 12px;
  background: #2d2d4a;
  color: #e0e0ff;
  border: 1px solid #534ab7;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1.2em;
  line-height: 1;
}
.menu-toggle:hover {
  background: #3d3d5a;
}
.app-main {
  min-height: calc(100vh - 56px);
  background: #0f0f1a;
  color: #e0e0ff;
}
.version {
  font-size: 0.6em;
  opacity: 0.6;
}

.mobile-menu {
  display: none;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .app-header {
    padding: 0 12px;
    height: 50px;
  }

  .app-header .top-nav {
    display: none;
  }

  .menu-toggle {
    display: block;
  }

  .app-header .header-right {
    flex: 1;
    justify-content: flex-end;
  }

  .user-info {
    display: none;
  }

  .logout-btn {
    padding: 6px 10px;
    font-size: 0.8em;
  }

  .lang-btn {
    margin-left: 8px;
    padding: 6px 10px;
    font-size: 0.8em;
  }

  .app-main {
    min-height: calc(100vh - 50px);
  }

  .mobile-menu {
    display: block;
    position: fixed;
    top: 50px;
    left: 0;
    right: 0;
    background: #1a1a2e;
    border-bottom: 1px solid #2d2d4a;
    z-index: 200;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }

  .mobile-nav {
    display: flex;
    flex-direction: column;
  }

  .mobile-nav a {
    color: #a0a0c0;
    text-decoration: none;
    padding: 14px 20px;
    border-bottom: 1px solid #2d2d4a;
    font-size: 0.95em;
  }

  .mobile-nav a:last-child {
    border-bottom: none;
  }

  .mobile-nav a.router-link-active {
    color: #7c5cff;
    background: rgba(124, 92, 255, 0.1);
  }
}

@media (max-width: 480px) {
  .app-header {
    height: 48px;
  }

  .mobile-menu {
    top: 48px;
  }

  .app-main {
    min-height: calc(100vh - 48px);
  }
}
</style>
