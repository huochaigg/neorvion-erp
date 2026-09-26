import { listUsableTenants, myTenantsQueryKey, SHELL_ROUTES } from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Select } from 'antd';
import { useNavigate } from 'react-router-dom';
import { fetchMyTenants } from '@/api/tenants';
import { switchTenant } from '@/lib/switch-tenant';
import { useTenantStore } from '@/stores/tenant-store';

export function TenantSwitcher() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const currentTenantId = useTenantStore((state) => state.currentTenantId);
  const isSwitching = useTenantStore((state) => state.isSwitching);
  const { data: tenants } = useQuery({
    queryKey: myTenantsQueryKey(),
    queryFn: ({ signal }) => fetchMyTenants(signal),
  });

  const usable = listUsableTenants(tenants ?? []);

  return (
    <Select
      className="min-w-[220px]"
      placeholder="选择企业"
      value={currentTenantId ?? undefined}
      disabled={isSwitching}
      popupMatchSelectWidth={false}
      options={usable.map((item) => ({
        value: item.id,
        label: `${item.name}（${item.code}） · ${item.my_role}`,
      }))}
      onChange={(tenantId: number) => {
        try {
          switchTenant(queryClient, tenantId);
        } catch (error) {
          message.error(error instanceof Error ? error.message : '无法切换企业');
          navigate(SHELL_ROUTES.workspaces);
        }
      }}
    />
  );
}
