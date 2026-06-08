"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { authApi } from "@/lib/api/auth";
import type { AuthState, LoginRequest, RegisterRequest, User } from "@/types/auth";

interface AuthContextValue extends AuthState {
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    isLoading: true,   // true until we check localStorage on mount
  });

  // ── Bootstrap: restore session from localStorage ──────────────────────────
  useEffect(() => {
    const accessToken = localStorage.getItem("access_token");
    const refreshToken = localStorage.getItem("refresh_token");

    if (!accessToken) {
      setState((s) => ({ ...s, isLoading: false }));
      return;
    }

    // Validate the stored token by fetching /users/me
    authApi
      .getMe()
      .then((user) => {
        setState({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
          isLoading: false,
        });
      })
      .catch(() => {
        // Token invalid or expired — clear storage
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        setState({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
        });
      });
  }, []);

  // ── Actions ───────────────────────────────────────────────────────────────

  const login = useCallback(async (data: LoginRequest) => {
    const result = await authApi.login(data);
    localStorage.setItem("access_token", result.tokens.access_token);
    localStorage.setItem("refresh_token", result.tokens.refresh_token);
    setState({
      user: result.user,
      accessToken: result.tokens.access_token,
      refreshToken: result.tokens.refresh_token,
      isAuthenticated: true,
      isLoading: false,
    });
  }, []);

  const register = useCallback(async (data: RegisterRequest) => {
    // Register creates the account (returns UserResponse, no tokens)
    await authApi.register(data);
    // Auto-login immediately after to get the token pair
    const result = await authApi.login({ email: data.email, password: data.password });
    localStorage.setItem("access_token", result.tokens.access_token);
    localStorage.setItem("refresh_token", result.tokens.refresh_token);
    setState({
      user: result.user,
      accessToken: result.tokens.access_token,
      refreshToken: result.tokens.refresh_token,
      isAuthenticated: true,
      isLoading: false,
    });
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        // Best-effort — always clear locally
      }
    }
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
    });
  }, []);

  const refreshUser = useCallback(async () => {
    const user = await authApi.getMe();
    setState((s) => ({ ...s, user }));
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuthContext must be used inside <AuthProvider>");
  return ctx;
}
