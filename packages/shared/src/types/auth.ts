export interface UserProfile {
  id: number;
  email: string;
  display_name: string;
  status: string;
  created_at: string;
  last_login_at: string | null;
  must_change_password: boolean;
}

export interface EncryptedPasswordPayload {
  encrypted_password: string;
  key_id: string;
  challenge_id: string;
}

export interface AuthPublicKey {
  key_id: string;
  public_key: string;
  algorithm: string;
  challenge_id: string;
  expires_in: number;
}

export interface TokenPayload {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export const AUTH_ERROR_CODE = {
  unauthenticated: 40100,
  invalidToken: 40102,
  expired: 40103,
  revoked: 40104,
} as const;

export const SESSION_EXPIRED_MESSAGE = '登录已过期，请重新登录';
