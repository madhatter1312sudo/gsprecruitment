/**
 * Auth session store (Zustand) backed by expo-secure-store.
 *
 * Backend note: POST /api/auth/login and /api/auth/register only ever
 * return a single `access_token` (JWT) — there is no separate refresh
 * token issued by talent-os/backend/routers/auth.py. `POST /api/auth/refresh`
 * simply re-validates whatever token you send it (access or refresh) and
 * mints a new access token from its claims, as long as it hasn't expired
 * yet. So we store the access token under both slots conceptually: we keep
 * it as `accessToken` and use the same value as the "refresh" candidate.
 * If refresh fails (expired token), we fall back to logging the user out.
 */
import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';

const ACCESS_TOKEN_KEY = 'gsp_access_token';
const USER_KEY = 'gsp_user';

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_verified: boolean;
}

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  hydrated: boolean;
  isAuthenticated: boolean;
  setSession: (accessToken: string, user: AuthUser) => Promise<void>;
  updateUser: (user: AuthUser) => void;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  hydrated: false,
  isAuthenticated: false,

  setSession: async (accessToken, user) => {
    set({ accessToken, user, isAuthenticated: true });
    try {
      await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken);
      await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user));
    } catch {
      // Storage failure shouldn't crash the session — it just won't survive a restart.
    }
  },

  updateUser: (user) => {
    set({ user });
    SecureStore.setItemAsync(USER_KEY, JSON.stringify(user)).catch(() => {});
  },

  logout: async () => {
    set({ accessToken: null, user: null, isAuthenticated: false });
    try {
      await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
      await SecureStore.deleteItemAsync(USER_KEY);
    } catch {
      // ignore
    }
  },

  hydrate: async () => {
    try {
      const [token, userJson] = await Promise.all([
        SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
        SecureStore.getItemAsync(USER_KEY),
      ]);
      if (token && userJson) {
        set({ accessToken: token, user: JSON.parse(userJson), isAuthenticated: true, hydrated: true });
        return;
      }
    } catch {
      // ignore — treat as logged out
    }
    set({ hydrated: true });
  },
}));

/** Non-hook accessor for use inside lib/api.ts (outside React render). */
export function getAuthState() {
  return useAuthStore.getState();
}
