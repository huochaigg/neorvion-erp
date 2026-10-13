import { KNOWLEDGE_DEFAULT_PATH, SHELL_EVENTS, type TenantChangedPayload } from '@neorvion/shared';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { isolateTenantQueries } from '@/lib/query-tenant';
import { getShellProps, isEmbeddedInWujie } from '@/lib/runtime';
import { useKnowledgeTenantStore } from '@/stores/tenant-runtime';

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

export function TenantChangeBridge() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const locationRef = useRef(location);
  locationRef.current = location;
  const hydrateFromShell = useKnowledgeTenantStore((state) => state.hydrateFromShell);
  const applyTenantChange = useKnowledgeTenantStore((state) => state.applyTenantChange);

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
      if (/^\/bases\/\d+\/?$/.test(locationRef.current.pathname)) {
        navigate(KNOWLEDGE_DEFAULT_PATH, { replace: true });
      }
    };

    eventBus.$on(SHELL_EVENTS.tenantChanged, onTenantChanged);
    return () => {
      eventBus.$off(SHELL_EVENTS.tenantChanged, onTenantChanged);
    };
  }, [applyTenantChange, navigate, queryClient]);

  return null;
}
