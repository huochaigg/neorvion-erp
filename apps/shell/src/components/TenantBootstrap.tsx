import {
  currentUserQueryKey,
  listUsableTenants,
  MICRO_EVENTS,
  myTenantsQueryKey,
  pickTenantSelection,
  SHELL_ROUTES,
  type Tenant,
  type UserProfile,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Spin } from 'antd';
import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { bus } from 'wujie';
import { fetchCurrentUser } from '@/api/auth';
import { fetchMyTenants } from '@/api/tenants';
import { applyCurrentTenant, clearTenantSelection } from '@/lib/switch-tenant';
import { readLastTenantId } from '@/lib/tenant-persist';
import { useAuthStore } from '@/stores/auth-store';
import { useTenantStore } from '@/stores/tenant-store';

interface TenantBootstrapProps {
  children: ReactNode;
}

function isWorkspacePath(pathname: string) {
  return pathname === SHELL_ROUTES.workspaces || pathname.startsWith(`${SHELL_ROUTES.workspaces}/`);
}

function reconcileTenantSelection(
  queryClient: ReturnType<typeof useQueryClient>,
  user: UserProfile,
  tenants: Tenant[],
) {
  const usable = listUsableTenants(tenants);
  const current = useTenantStore.getState().currentTenantId;
  if (current != null && !usable.some((item) => item.id === current)) {
    applyCurrentTenant(queryClient, null);
  }

  const nextCurrent = useTenantStore.getState().currentTenantId;
  if (nextCurrent != null) {
    return;
  }

  const pick = pickTenantSelection(tenants, readLastTenantId(user.id));
  if (pick.kind === 'select') {
    applyCurrentTenant(queryClient, pick.tenantId);
  }
}

export function TenantBootstrap({ children }: TenantBootstrapProps) {
  const location = useLocation();
  const queryClient = useQueryClient();
  const accessToken = useAuthStore((state) => state.accessToken);
  const currentTenantId = useTenantStore((state) => state.currentTenantId);
  const bootstrapped = useTenantStore((state) => state.bootstrapped);
  const markBootstrapped = useTenantStore((state) => state.markBootstrapped);

  const { data: currentUser, isLoading: userLoading } = useQuery({
    queryKey: currentUserQueryKey(),
    queryFn: fetchCurrentUser,
    enabled: Boolean(accessToken),
  });
  const { data: tenants, isLoading: tenantsLoading, isError, error, refetch } = useQuery({
    queryKey: myTenantsQueryKey(),
    queryFn: ({ signal }) => fetchMyTenants(signal),
    enabled: Boolean(accessToken),
  });

  useEffect(() => {
    if (!currentUser || !tenants) {
      return;
    }
    reconcileTenantSelection(queryClient, currentUser, tenants);
    markBootstrapped();
  }, [currentUser, markBootstrapped, queryClient, tenants]);

  useEffect(() => {
    const onInaccessible = () => {
      clearTenantSelection(queryClient, { persist: true });
      void queryClient.invalidateQueries({ queryKey: myTenantsQueryKey() });
    };
    bus.$on(MICRO_EVENTS.tenantInaccessible, onInaccessible);
    return () => {
      bus.$off(MICRO_EVENTS.tenantInaccessible, onInaccessible);
    };
  }, [queryClient]);

  if (isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f3f5f8] p-6">
        <Alert
          type="error"
          showIcon
          title="无法加载工作空间"
          description={error instanceof Error ? error.message : '请稍后重试'}
          action={
            <Button size="small" onClick={() => void refetch()}>
              重试
            </Button>
          }
        />
      </div>
    );
  }

  if (!bootstrapped || userLoading || tenantsLoading || !currentUser || !tenants) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f3f5f8] text-sm text-slate-500">
        <Spin />
        <span className="ml-3">正在加载工作空间…</span>
      </div>
    );
  }

  const usable = listUsableTenants(tenants);
  const pick = pickTenantSelection(tenants, readLastTenantId(currentUser.id));
  const workspacePath = isWorkspacePath(location.pathname);

  if (currentTenantId != null && !usable.some((item) => item.id === currentTenantId)) {
    return <Navigate to={SHELL_ROUTES.workspaces} replace />;
  }

  if (currentTenantId == null && pick.kind === 'none' && location.pathname !== SHELL_ROUTES.workspaceCreate) {
    return <Navigate to={SHELL_ROUTES.workspaceCreate} replace />;
  }

  if (currentTenantId == null && pick.kind === 'choose' && !workspacePath) {
    return <Navigate to={SHELL_ROUTES.workspaces} replace />;
  }

  return children;
}
