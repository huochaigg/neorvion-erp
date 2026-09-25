import { create } from 'zustand';

interface ShellState {
  siderCollapsed: boolean;
  currentTenantId: number | null;
  toggleSider: () => void;
  setCurrentTenantId: (tenantId: number | null) => void;
}

export const useShellStore = create<ShellState>((set) => ({
  siderCollapsed: false,
  currentTenantId: null,
  toggleSider: () => set((state) => ({ siderCollapsed: !state.siderCollapsed })),
  setCurrentTenantId: (currentTenantId) => set({ currentTenantId }),
}));
