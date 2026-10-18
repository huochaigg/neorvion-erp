import { Tabs as ChromeTabs } from '@sinm/react-chrome-tabs';
import '@sinm/react-chrome-tabs/css/chrome-tabs.css';
import { Dropdown } from 'antd';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type MouseEvent,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { usePermissions } from '@/hooks/usePermissions';
import { getPopupContainer } from '@/lib/runtime';
import { pageAllowsAccess } from '@/router/access';
import { matchRoute } from '@/router/match';
import { routes } from '@/router/routes';
import { DASHBOARD_TAB_PATH, shouldSkipTabAfterTenantChange } from '@/router/tab-utils';
import { useTabsStore } from '@/stores/tabs-store';
import { useErpTenantStore } from '@/stores/tenant-runtime';
import styles from './TabBar.module.scss';

function useTabsHydrated() {
  const [hydrated, setHydrated] = useState(() => useTabsStore.persist.hasHydrated());
  useEffect(() => {
    if (hydrated) {
      return undefined;
    }
    return useTabsStore.persist.onFinishHydration(() => {
      setHydrated(true);
    });
  }, [hydrated]);
  return hydrated;
}

export function TabBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const hydrated = useTabsHydrated();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const { permissions, isLoading } = usePermissions();
  const tabs = useTabsStore((state) => state.tabs);
  const activeKey = useTabsStore((state) => state.activeKey);
  const draggingRef = useRef(false);
  const [contextKey, setContextKey] = useState<string | null>(null);

  useEffect(() => {
    if (!hydrated) {
      return;
    }
    const store = useTabsStore.getState();
    if (store.tenantId !== tenantId) {
      store.resetForTenant(tenantId);
      if (shouldSkipTabAfterTenantChange(location.pathname, routes)) {
        return;
      }
    }
    store.ensureFromLocation(location.pathname);
  }, [hydrated, location.pathname, tenantId]);

  useEffect(() => {
    if (!hydrated || isLoading) {
      return;
    }
    const nextKey = useTabsStore.getState().pruneForbidden(permissions);
    const match = matchRoute(routes, location.pathname);
    if (match && !pageAllowsAccess(match, permissions) && nextKey !== location.pathname) {
      navigate(nextKey, { replace: true });
    }
  }, [hydrated, isLoading, location.pathname, navigate, permissions]);

  const go = useCallback(
    (key: string) => {
      if (key !== location.pathname) {
        navigate(key);
      }
    },
    [location.pathname, navigate],
  );

  const closeKey = useCallback(
    (key: string) => {
      const wasActive = useTabsStore.getState().activeKey === key;
      const next = useTabsStore.getState().close(key);
      if (wasActive && next !== location.pathname) {
        navigate(next);
      }
    },
    [location.pathname, navigate],
  );

  const chromeTabs = useMemo<ComponentProps<typeof ChromeTabs>['tabs']>(
    () =>
      tabs.map((tab) => ({
        id: tab.key,
        title: tab.title,
        active: tab.key === activeKey,
        favicon: false,
        isCloseIconVisible: tab.closable,
      })),
    [activeKey, tabs],
  );

  const contextTab = tabs.find((item) => item.key === contextKey);
  const contextIndex = tabs.findIndex((item) => item.key === contextKey);
  const hasClosableRight =
    contextIndex >= 0 && tabs.slice(contextIndex + 1).some((item) => item.closable);

  return (
    <Dropdown
      trigger={['contextMenu']}
      getPopupContainer={getPopupContainer}
      menu={{
        items: [
          {
            key: 'close',
            label: '删除当前',
            disabled: !contextTab?.closable,
          },
          {
            key: 'closeRight',
            label: '删除右侧',
            disabled: !hasClosableRight,
          },
          { key: 'closeAll', label: '清除全部' },
        ],
        onClick: ({ key, domEvent }) => {
          (domEvent as MouseEvent).preventDefault();
          const targetKey = contextKey;
          setContextKey(null);
          if (!targetKey) {
            return;
          }
          const store = useTabsStore.getState();
          if (key === 'close') {
            closeKey(targetKey);
            return;
          }
          if (key === 'closeRight') {
            const next = store.closeToTheRight(targetKey);
            if (next !== location.pathname) {
              navigate(next);
            }
            return;
          }
          const next = store.closeAll();
          if (next !== location.pathname) {
            navigate(next);
          }
        },
      }}
    >
      <div
        className={styles.wrap}
        onContextMenu={(event) => {
          const tabEl = (event.target as HTMLElement | null)?.closest('[data-tab-id]');
          const id = tabEl instanceof HTMLElement ? tabEl.getAttribute('data-tab-id') : null;
          if (!id) {
            event.preventDefault();
            event.stopPropagation();
            setContextKey(null);
            return;
          }
          event.preventDefault();
          setContextKey(id);
        }}
      >
        <ChromeTabs
          className={styles.chrome}
          draggable
          darkMode={false}
          tabs={chromeTabs}
          onDragBegin={() => {
            draggingRef.current = true;
          }}
          onDragEnd={() => {
            draggingRef.current = false;
          }}
          onTabActive={(id) => {
            if (draggingRef.current) {
              return;
            }
            go(id);
          }}
          onTabClose={closeKey}
          onTabReorder={(id, fromIndex, toIndex) => {
            if (id === DASHBOARD_TAB_PATH || fromIndex === 0) {
              return;
            }
            const keys = tabs.map((item) => item.key);
            const [moved] = keys.splice(fromIndex, 1);
            if (!moved) {
              return;
            }
            keys.splice(toIndex, 0, moved);
            useTabsStore.getState().reorder(keys);
          }}
        />
      </div>
    </Dropdown>
  );
}
