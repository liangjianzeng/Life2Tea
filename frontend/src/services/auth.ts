/**
 * auth.ts — Authentication service for the frontend.
 *
 * Provides functions to:
 * - Check if admin is initialized
 * - Initialize admin (first-time setup)
 * - Login with email/password
 * - Logout
 * - Check current authentication status
 */

const API_BASE = "/api";

export interface AuthStatus {
  initialized: boolean;
  user: {
    id: string;
    email: string;
    is_admin: boolean;
  } | null;
}

/**
 * Check if the admin user is initialized.
 */
export async function checkInitStatus(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/status`, {
      credentials: "include",
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data.initialized;
  } catch {
    return false;
  }
}

/**
 * Check current authentication status.
 */
export async function checkAuth(): Promise<AuthStatus> {
  try {
    const res = await fetch(`${API_BASE}/auth/whoami`, {
      credentials: "include",
    });
    if (!res.ok) {
      return { initialized: false, user: null };
    }
    return await res.json();
  } catch {
    return { initialized: false, user: null };
  }
}

/**
 * Initialize admin user (first-time setup).
 */
export async function initializeAdmin(email: string, password: string): Promise<{ ok: boolean; message?: string }> {
  try {
    const res = await fetch(`${API_BASE}/auth/init`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });

    if (res.ok) {
      return { ok: true };
    } else {
      const data = await res.json();
      return { ok: false, message: data.detail || "Failed to initialize admin" };
    }
  } catch (e: any) {
    return { ok: false, message: e.message || "Network error" };
  }
}

/**
 * Login with email and password.
 */
export async function login(email: string, password: string): Promise<{ ok: boolean; user?: any }> {
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });

    if (res.ok) {
      const data = await res.json();
      return { ok: true, user: data.user };
    } else {
      return { ok: false };
    }
  } catch (e: any) {
    return { ok: false };
  }
}

/**
 * Logout.
 */
export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // Ignore errors
  }
}
