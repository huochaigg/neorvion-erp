import {
  SHELL_EVENTS,
  safePathAfterTenantChange,
  type TenantChangedPayload,
} from '@neorvion/shared';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { isolateTenantQueries } from '@/lib/query-tenant';
import { getShellProps, isEmbeddedInWujie } from '@/lib/runtime';
import { useErpTenantStore } from '@/stores/tenant-runtime';

function isTenantChangedPayload(value: unknown): value is TenantChangedPayload {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const payload = value as TenantChangedPayload;
  return (
    (payload.previousTenantId === null || typeof payload.previousTenantId === 'number') &&
    (payload.currentTenantId === null || typeof payload.currentTenantId === 'number')
  );
}

/** 统一处理租户变化：隔离 Query、重置页面局部状态、必要时离开带资源 ID 的路由。 */
export function TenantChangeBridge() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const locationRef = useRef(location);
  locationRef.current = location;
  const hydrateFromShell = useErpTenantStore((state) => state.hydrateFromShell);
  const applyTenantChange = useErpTenantStore((state) => state.applyTenantChange);

  useEffect(() => {
    hydrateFromShell(getShellProps().tenantId);
  }, [hydrateFromShell]);

  useEffect(() => {
    if (!isEmbeddedInWujie()) {
      return undefined;
    }
    const eventBus = window.$wujie?.bus;
    if (!eventBus) {
      return undefined;
    }

    const onTenantChanged = (...args: unknown[]) => {
      const payload = args[0];
      if (!isTenantChangedPayload(payload)) {
        return;
      }
      isolateTenantQueries(queryClient, payload.previousTenantId);
      applyTenantChange(payload.currentTenantId);
      const fallback = safePathAfterTenantChange(locationRef.current.pathname);
      if (fallback) {
        navigate(fallback, { replace: true });
      }
    };

    eventBus.$on(SHELL_EVENTS.tenantChanged, onTenantChanged);
    return () => {
      eventBus.$off(SHELL_EVENTS.tenantChanged, onTenantChanged);
    };
  }, [applyTenantChange, navigate, queryClient]);

  return null;
}
