<template>
  <div class="login-container">
    <div class="login-card">
      <h2>{{ t("auth.loginTitle") }}</h2>
      <p class="login-subtitle">{{ t("auth.loginSubtitle") }}</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="email">{{ t("auth.email") }}</label>
          <input
            id="email"
            v-model="email"
            type="email"
            :placeholder="t('auth.emailPlaceholder')"
            required
            autocomplete="email"
          />
        </div>

        <div class="form-group">
          <label for="password">{{ t("auth.password") }}</label>
          <input
            id="password"
            v-model="password"
            type="password"
            :placeholder="t('auth.passwordPlaceholder')"
            required
            autocomplete="current-password"
          />
        </div>

        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? t("auth.loggingIn") : t("auth.loginButton") }}
        </button>
      </form>

      <div v-if="error" class="error-message">{{ error }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { checkAuth, login as apiLogin } from "../services/auth";

const { t } = useI18n();
const router = useRouter();

const email = ref("");
const password = ref("");
const loading = ref(false);
const error = ref("");

async function handleLogin() {
  loading.value = true;
  error.value = "";

  try {
    const result = await apiLogin(email.value, password.value);
    if (result.ok) {
      router.push("/");
    } else {
      error.value = t("auth.loginError");
    }
  } catch (e: any) {
    error.value = e.message || t("auth.loginError");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
  padding: 20px;
}

.login-card {
  background: #1a1a2e;
  border: 1px solid #534ab7;
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.login-card h2 {
  text-align: center;
  color: #7c5cff;
  margin: 0 0 8px 0;
  font-size: 1.5em;
}

.login-subtitle {
  text-align: center;
  color: #888;
  margin: 0 0 32px 0;
  font-size: 0.9em;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  color: #aaa;
  font-size: 0.85em;
  font-weight: 500;
}

.form-group input {
  padding: 12px 16px;
  background: #0d0d1a;
  border: 1px solid #2d2d4a;
  border-radius: 8px;
  color: #e0e0ff;
  font-size: 1em;
  transition: border-color 0.2s;
}

.form-group input:focus {
  outline: none;
  border-color: #534ab7;
}

.btn-primary {
  padding: 12px;
  background: #534ab7;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 1em;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
  margin-top: 8px;
}

.btn-primary:hover:not(:disabled) {
  background: #6b5cc4;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-message {
  margin-top: 16px;
  padding: 12px;
  background: #3a1a1a;
  border: 1px solid #4a2d2d;
  border-radius: 8px;
  color: #f44336;
  font-size: 0.9em;
  text-align: center;
}
</style>
