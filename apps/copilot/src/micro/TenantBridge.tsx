import { SHELL_EVENTS, isTenantChangedPayload } from '@neorvion/shared';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { shellProps } from '@/runtime';
import { useCopilotStore } from '@/store';

export function TenantBridge() {
  const query = useQueryClient();
  const switchTenant = useCopilotStore((s) => s.switchTenant);

  useEffect(() => {
    const tenantId = shellProps().tenantId;
    if (tenantId !== useCopilotStore.getState().tenantId) {
      switchTenant(tenantId);
    }
  }, [switchTenant]);

  useEffect(() => {
    const bus = window.$wujie?.bus;
    if (!bus) {
      return undefined;
    }
    const onChange = (raw: unknown) => {
      if (!isTenantChangedPayload(raw)) {
        return;
      }
      query.clear();
      switchTenant(raw.currentTenantId);
    };
    bus.$on(SHELL_EVENTS.tenantChanged, onChange);
    return () => bus.$off(SHELL_EVENTS.tenantChanged, onChange);
  }, [query, switchTenant]);

  return null;
}
