import { createRouter, createWebHistory } from "vue-router";
import { checkAuth } from "./services/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "Chat",
      component: () => import("./views/ChatView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/dashboard",
      name: "Dashboard",
      component: () => import("./views/DashboardView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/models",
      name: "Models",
      component: () => import("./views/ModelsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/plugins",
      name: "Plugins",
      component: () => import("./views/PluginsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/settings",
      name: "Settings",
      component: () => import("./views/SettingsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/api-keys",
      name: "API Keys",
      component: () => import("./views/ApiKeysView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/logs",
      name: "Logs",
      component: () => import("./views/LogManagementView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/login",
      name: "Login",
      component: () => import("./views/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/setup",
      name: "Setup",
      component: () => import("./views/SetupView.vue"),
      meta: { public: true },
    },
  ],
});

// Auth guard
router.beforeEach(async (to, _from) => {
  const publicRoutes = ["/login", "/setup"];
  const isPublic = publicRoutes.includes(to.path);

  if (to.meta.requiresAuth && !isPublic) {
    // Check authentication status
    const auth = await checkAuth();
    if (!auth.user) {
      // Not authenticated — redirect to login or setup
      if (auth.initialized) {
        return { name: "Login" };
      } else {
        return { name: "Setup" };
      }
    }
  }

  // If visiting public routes
  if (isPublic) {
    const auth = await checkAuth();

    // If already logged in, redirect to home
    if (auth.user) {
      return { path: "/" };
    }

    // If database is initialized but user is not logged in, redirect to login
    if (to.path === "/setup" && auth.initialized) {
      return { name: "Login" };
    }
  }
});

export default router;
