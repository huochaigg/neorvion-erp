import { create } from 'zustand';

export type AuthStatus = 'initializing' | 'authenticated' | 'unauthenticated';

interface AuthState {
  accessToken: string | null;
  status: AuthStatus;
  markAuthenticated: (token: string) => void;
  markUnauthenticated: () => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  status: 'initializing',
  markAuthenticated: (accessToken) => set({ accessToken, status: 'authenticated' }),
  markUnauthenticated: () => set({ accessToken: null, status: 'unauthenticated' }),
  reset: () => set({ accessToken: null, status: 'unauthenticated' }),
}));
