import apiClient from "./client";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  email: string;
  display_name: string;
  role: string;
  created_at: string | null;
}

export async function login(data: LoginRequest): Promise<TokenResponse> {
  const { data: response } = await apiClient.post<TokenResponse>(
    "/auth/login",
    data
  );
  return response;
}

export async function register(data: RegisterRequest): Promise<UserResponse> {
  const { data: response } = await apiClient.post<UserResponse>(
    "/auth/register",
    data
  );
  return response;
}

export async function getMe(): Promise<UserResponse> {
  const { data } = await apiClient.get<UserResponse>("/auth/me");
  return data;
}

export async function refreshToken(
  refresh_token: string
): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/refresh", {
    refresh_token,
  });
  return data;
}
