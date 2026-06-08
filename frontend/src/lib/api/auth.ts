import apiClient from "./axios";
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  User,
} from "@/types/auth";

export const authApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>(
      "/api/v1/auth/login",
      data
    );
    return response.data;
  },

  register: async (data: RegisterRequest): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>(
      "/api/v1/auth/register",
      data
    );
    return response.data;
  },

  logout: async (refreshToken: string): Promise<void> => {
    await apiClient.post("/api/v1/auth/logout", {
      refresh_token: refreshToken,
    });
  },

  getMe: async (): Promise<User> => {
    const response = await apiClient.get<User>("/api/v1/users/me");
    return response.data;
  },

  updateProfile: async (data: {
    full_name?: string;
  }): Promise<User> => {
    const response = await apiClient.patch<User>("/api/v1/users/me", data);
    return response.data;
  },

  changePassword: async (data: {
    current_password: string;
    new_password: string;
  }): Promise<void> => {
    await apiClient.post("/api/v1/users/me/change-password", data);
  },

  deleteAccount: async (password: string): Promise<void> => {
    await apiClient.delete("/api/v1/users/me", {
      data: { password },
    });
  },
};
