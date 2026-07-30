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
      path: "/dashboard",
      name: "Dashboard",
      component: () => import("./views/DashboardView.vue"),
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
    {
      path: "/logs",
      name: "Logs",
      component: () => import("./views/LogManagementView.vue"),
    },
    {
      path: "/login",
      name: "Login",
      component: () => import("./views/LoginView.vue"),
    },
    {
      path: "/setup",
      name: "Setup",
      component: () => import("./views/SetupView.vue"),
    },
  ],
});


export default router;
