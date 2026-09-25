import { create } from 'zustand';

interface AuthState {
  accessToken: string | null;
  hydrated: boolean;
  setAccessToken: (token: string | null) => void;
  setHydrated: (hydrated: boolean) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  hydrated: false,
  setAccessToken: (accessToken) => set({ accessToken }),
  setHydrated: (hydrated) => set({ hydrated }),
  reset: () => set({ accessToken: null }),
}));
