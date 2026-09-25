export interface UserProfile {
  id: number;
  email: string;
  display_name: string;
  status: string;
  created_at: string;
  last_login_at: string | null;
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
