import { create } from 'zustand';

interface TenantState {
  currentTenantId: number | null;
  isSwitching: boolean;
  bootstrapped: boolean;
  setCurrentTenantId: (tenantId: number | null) => void;
  beginSwitch: () => void;
  endSwitch: () => void;
  markBootstrapped: () => void;
  clearCurrentTenant: () => void;
  reset: () => void;
}

export const useTenantStore = create<TenantState>((set) => ({
  currentTenantId: null,
  isSwitching: false,
  bootstrapped: false,
  setCurrentTenantId: (currentTenantId) => set({ currentTenantId }),
  beginSwitch: () => set({ isSwitching: true }),
  endSwitch: () => set({ isSwitching: false }),
  markBootstrapped: () => set({ bootstrapped: true }),
  clearCurrentTenant: () => set({ currentTenantId: null, isSwitching: false }),
  reset: () => set({ currentTenantId: null, isSwitching: false, bootstrapped: false }),
}));
