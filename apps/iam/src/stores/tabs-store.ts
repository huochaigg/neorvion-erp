import { create } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';
import { routes } from '@/router/routes';
import {
  closeAllTabs,
  closeOtherTabs,
  closeTab,
  closeTabsToTheRight,
  createInitialTabsState,
  ensureTab,
  pruneInvalidTabs,
  reorderTabs,
  resetTabsForTenant,
  setTabTitle,
  type RouteTab,
  type TabsSnapshot,
} from '@/router/tab-utils';

export const TABS_STORAGE_KEY = 'neorvion.erp.tabs.v1';

function memoryStorage(): StateStorage {
  const map = new Map<string, string>();
  return {
    getItem: (name) => map.get(name) ?? null,
    setItem: (name, value) => {
      map.set(name, value);
    },
    removeItem: (name) => {
      map.delete(name);
    },
  };
}

function tabsStorage(): StateStorage {
  if (typeof window === 'undefined' || !window.localStorage) {
    return memoryStorage();
  }
  return window.localStorage;
}

interface TabsStore extends TabsSnapshot {
  ensureFromLocation: (pathname: string) => void;
  close: (key: string) => string;
  closeOthers: (key?: string) => string;
  closeAll: () => string;
  closeToTheRight: (key: string) => string;
  setTitle: (pathname: string, title: string) => void;
  resetForTenant: (tenantId: number | null) => void;
  pruneUnknown: () => void;
  pruneForbidden: (permissions: readonly string[]) => string;
  reorder: (orderedKeys: string[]) => void;
}

export const useTabsStore = create<TabsStore>()(
  persist(
    (set, get) => ({
      ...createInitialTabsState(),
      ensureFromLocation: (pathname) => {
        set((state) => ensureTab(state, pathname, routes));
      },
      close: (key) => {
        set((state) => closeTab(state, key));
        return get().activeKey;
      },
      closeOthers: (key) => {
        set((state) => closeOtherTabs(state, key));
        return get().activeKey;
      },
      closeAll: () => {
        set((state) => closeAllTabs(state));
        return get().activeKey;
      },
      closeToTheRight: (key) => {
        set((state) => closeTabsToTheRight(state, key));
        return get().activeKey;
      },
      setTitle: (pathname, title) => {
        set((state) => setTabTitle(state, pathname, title));
      },
      resetForTenant: (tenantId) => {
        set(resetTabsForTenant(tenantId));
      },
      pruneUnknown: () => {
        set((state) => pruneInvalidTabs(state, routes));
      },
      pruneForbidden: (permissions) => {
        set((state) => pruneInvalidTabs(state, routes, permissions));
        return get().activeKey;
      },
      reorder: (orderedKeys) => {
        set((state) => reorderTabs(state, orderedKeys));
      },
    }),
    {
      name: TABS_STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(tabsStorage),
      partialize: (state) => ({
        tenantId: state.tenantId,
        tabs: state.tabs,
        activeKey: state.activeKey,
      }),
      merge: (persisted, current) => {
        const snapshot = persisted as Partial<TabsSnapshot> | undefined;
        if (!snapshot || !Array.isArray(snapshot.tabs)) {
          return current;
        }
        const restored = pruneInvalidTabs(
          {
            tenantId: snapshot.tenantId ?? null,
            tabs: snapshot.tabs as RouteTab[],
            activeKey: snapshot.activeKey ?? current.activeKey,
          },
          routes,
        );
        return { ...current, ...restored };
      },
    },
  ),
);
