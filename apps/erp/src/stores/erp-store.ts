import { create } from 'zustand';

interface ErpState {
  siderCollapsed: boolean;
  setSiderCollapsed: (collapsed: boolean) => void;
}

export const useErpStore = create<ErpState>((set) => ({
  siderCollapsed: false,
  setSiderCollapsed: (siderCollapsed) => set({ siderCollapsed }),
}));
