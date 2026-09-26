import { create } from 'zustand';
import { destroyAllMicroApps } from '@/micro/lifecycle';

interface ShellState {
  siderCollapsed: boolean;
  currentTenantId: number | null;
  toggleSider: () => void;
  setCurrentTenantId: (tenantId: number | null) => void;
}

export const useShellStore = create<ShellState>((set, get) => ({
  siderCollapsed: false,
  currentTenantId: null,
  toggleSider: () => set((state) => ({ siderCollapsed: !state.siderCollapsed })),
  setCurrentTenantId: (currentTenantId) => {
    const previous = get().currentTenantId;
    set({ currentTenantId });
    if (previous !== currentTenantId) {
      destroyAllMicroApps();
    }
  },
}));
