import { create } from 'zustand';
import { getShellProps } from '@/lib/runtime';

interface ErpTenantState {
  currentTenantId: number | null;
  epoch: number;
  hydrateFromShell: (tenantId: number | null) => void;
  applyTenantChange: (tenantId: number | null) => void;
}

export const useErpTenantStore = create<ErpTenantState>((set, get) => ({
  currentTenantId: getShellProps().tenantId,
  epoch: 0,
  hydrateFromShell: (currentTenantId) => {
    if (get().currentTenantId === currentTenantId) {
      return;
    }
    set({ currentTenantId });
  },
  applyTenantChange: (currentTenantId) => {
    if (get().currentTenantId === currentTenantId) {
      return;
    }
    set((state) => ({ currentTenantId, epoch: state.epoch + 1 }));
  },
}));
