import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "Chat",
      component: () => import("./views/ChatView.vue"),
    },
    {
      path: "/models",
      name: "Models",
      component: () => import("./views/ModelsView.vue"),
    },
    {
      path: "/plugins",
      name: "Plugins",
      component: () => import("./views/PluginsView.vue"),
    },
    {
      path: "/settings",
      name: "Settings",
      component: () => import("./views/SettingsView.vue"),
    },
    {
      path: "/api-keys",
      name: "API Keys",
      component: () => import("./views/ApiKeysView.vue"),
    },
  ],
});

export default router;
