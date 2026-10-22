import { create } from 'zustand';
import { shellProps } from './runtime';

interface State {
  tenantId: number | null;
  epoch: number;
  controller: AbortController | null;
  selectedId: number | null;
  sidebarCollapsed: boolean;
  setController: (value: AbortController | null) => void;
  setSelectedId: (id: number | null) => void;
  setSidebarCollapsed: (value: boolean | ((prev: boolean) => boolean)) => void;
  switchTenant: (id: number | null) => void;
  reset: () => void;
}

export const useCopilotStore = create<State>((set, get) => ({
  tenantId: shellProps().tenantId,
  epoch: 0,
  controller: null,
  selectedId: null,
  sidebarCollapsed: false,
  setController: (controller) => set({ controller }),
  setSelectedId: (selectedId) => set({ selectedId }),
  setSidebarCollapsed: (value) =>
    set({ sidebarCollapsed: typeof value === 'function' ? value(get().sidebarCollapsed) : value }),
  switchTenant: (tenantId) => {
    get().controller?.abort();
    set((s) => ({ tenantId, epoch: s.epoch + 1, controller: null, selectedId: null }));
  },
  reset: () => {
    get().controller?.abort();
    set((s) => ({ epoch: s.epoch + 1, controller: null, selectedId: null }));
  },
}));
