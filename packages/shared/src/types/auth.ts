export interface UserProfile {
  id: number;
  email: string;
  display_name: string;
  status: string;
  created_at: string;
  last_login_at: string | null;
}

export interface TokenPayload {
  access_token: string;
  token_type: string;
  expires_in: number;
}
