import { Result, Spin } from 'antd';
import { useMemo, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { usePermissions } from '@/hooks/usePermissions';
import { resolvePageAccessState } from '@/router/access';
import { matchRoute } from '@/router/match';
import { routes } from '@/router/routes';

function PageLoading() {
  return (
    <div className="flex min-h-[240px] items-center justify-center">
      <Spin />
    </div>
  );
}

export function ForbiddenPage() {
  return (
    <Result
      status="403"
      title="无权限"
      subTitle="当前企业身份无法访问该页面。这不是登录失效，请联系管理员分配角色。"
    />
  );
}

export function PermissionGuard({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { tenantId, permissions, isLoading } = usePermissions();
  const match = useMemo(() => matchRoute(routes, location.pathname), [location.pathname]);
  const state = resolvePageAccessState({
    tenantId,
    isLoading,
    match,
    permissions,
  });

  if (state === 'loading') {
    return <PageLoading />;
  }
  if (state === 'forbidden') {
    return <ForbiddenPage />;
  }
  return children;
}
