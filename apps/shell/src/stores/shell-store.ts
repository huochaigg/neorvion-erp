import { create } from 'zustand';

interface ShellState {
  siderCollapsed: boolean;
  toggleSider: () => void;
}

export const useShellStore = create<ShellState>((set) => ({
  siderCollapsed: false,
  toggleSider: () => set((state) => ({ siderCollapsed: !state.siderCollapsed })),
}));
