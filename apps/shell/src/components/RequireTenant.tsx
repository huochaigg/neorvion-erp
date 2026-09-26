import { SHELL_ROUTES } from '@neorvion/shared';
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useTenantStore } from '@/stores/tenant-store';

interface RequireTenantProps {
  children: ReactNode;
}

export function RequireTenant({ children }: RequireTenantProps) {
  const currentTenantId = useTenantStore((state) => state.currentTenantId);
  const isSwitching = useTenantStore((state) => state.isSwitching);

  if (isSwitching) {
    return children;
  }
  if (currentTenantId == null) {
    return <Navigate to={SHELL_ROUTES.workspaces} replace />;
  }
  return children;
}
