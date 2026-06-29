import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendUrl = env.VITE_BACKEND_URL || "http://127.0.0.1:3003";
  const frontendPort = parseInt(env.VITE_FRONTEND_PORT || "5005");

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      port: frontendPort,
      proxy: {
        "/api": {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            echarts: ["echarts"],
            vueVendor: ["vue", "vue-router", "vue-i18n", "pinia"],
          },
        },
      },
    },
  };
});
