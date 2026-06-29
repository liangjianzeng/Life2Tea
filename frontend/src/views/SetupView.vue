<template>
  <div class="setup-container">
    <div class="setup-card">
      <div class="setup-header">
        <h2>{{ t("auth.setupTitle") }}</h2>
        <p class="setup-subtitle">{{ t("auth.setupSubtitle") }}</p>
      </div>

      <form @submit.prevent="handleSetup" class="setup-form">
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
            minlength="6"
            autocomplete="new-password"
          />
          <small v-if="password" class="password-hint">{{ t("auth.passwordHint") }}</small>
        </div>

        <div class="form-group">
          <label for="confirmPassword">{{ t("auth.confirmPassword") }}</label>
          <input
            id="confirmPassword"
            v-model="confirmPassword"
            type="password"
            :placeholder="t('auth.confirmPasswordPlaceholder')"
            required
            autocomplete="new-password"
          />
          <small v-if="confirmPassword && password !== confirmPassword" class="error-text">
            {{ t("auth.passwordMismatch") }}
          </small>
        </div>

        <button type="submit" class="btn-primary" :disabled="loading || password !== confirmPassword">
          {{ loading ? t("auth.settingUp") : t("auth.setupButton") }}
        </button>
      </form>

      <div v-if="error" class="error-message">{{ error }}</div>
      <div v-if="success" class="success-message">{{ success }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { initializeAdmin } from "../services/auth";

const { t } = useI18n();
const router = useRouter();

const email = ref("");
const password = ref("");
const confirmPassword = ref("");
const loading = ref(false);
const error = ref("");
const success = ref("");

async function handleSetup() {
  if (password.value !== confirmPassword.value) {
    error.value = t("auth.passwordMismatch");
    return;
  }

  loading.value = true;
  error.value = "";
  success.value = "";

  try {
    const result = await initializeAdmin(email.value, password.value);
    if (result.ok) {
      success.value = t("auth.setupSuccess");
      setTimeout(() => {
        router.push("/");
      }, 1000);
    } else {
      error.value = result.message || t("auth.setupError");
    }
  } catch (e: any) {
    error.value = e.message || t("auth.setupError");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.setup-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
  padding: 20px;
}

.setup-card {
  background: #1a1a2e;
  border: 1px solid #534ab7;
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.setup-header {
  text-align: center;
  margin-bottom: 32px;
}

.setup-header h2 {
  color: #7c5cff;
  margin: 0 0 8px 0;
  font-size: 1.5em;
}

.setup-subtitle {
  color: #888;
  margin: 0;
  font-size: 0.9em;
}

.setup-form {
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

.form-group small {
  font-size: 0.8em;
  color: #666;
}

.password-hint {
  color: #fbbf24 !important;
}

.error-text {
  color: #f44336 !important;
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

.success-message {
  margin-top: 16px;
  padding: 12px;
  background: #1a3a1a;
  border: 1px solid #2d4a2d;
  border-radius: 8px;
  color: #4caf50;
  font-size: 0.9em;
  text-align: center;
}
</style>
