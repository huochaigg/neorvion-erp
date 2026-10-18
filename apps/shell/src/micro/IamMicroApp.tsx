import { currentUserQueryKey, IAM_APP_NAME, type ShellToErpProps } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button } from 'antd';
import { useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { refreshSessionFromShell } from '@/api/client';
import { fetchCurrentUser } from '@/api/auth';
import { buildMicroAppUrl, getMicroApp } from '@/micro/apps';
import { consumeLegacyWujieSyncQuery, emitHostNavigate, useMicroHostRouteSync } from '@/micro/route-sync';
import { WujieHost } from '@/micro/wujie-host';
import { useAuthStore } from '@/stores/auth-store';
import { useTenantStore } from '@/stores/tenant-store';

export function IamMicroApp() {
  const location = useLocation();
  const tenantId = useTenantStore((state) => state.currentTenantId);
  const accessToken = useAuthStore((state) => state.accessToken);
  const [loadFailed, setLoadFailed] = useState(false);
  const { data: currentUser } = useQuery({
    queryKey: currentUserQueryKey(),
    queryFn: fetchCurrentUser,
    enabled: Boolean(accessToken),
  });

  const app = getMicroApp(IAM_APP_NAME);
  const legacyTarget = consumeLegacyWujieSyncQuery(app, location);
  const url = buildMicroAppUrl(app, location.pathname, location.search, location.hash);

  useMicroHostRouteSync(app);

  const props = useMemo<ShellToErpProps>(
    () => ({
      token: accessToken,
      tenantId,
      user: currentUser ? { id: currentUser.id, displayName: currentUser.display_name } : null,
      refreshSession: refreshSessionFromShell,
    }),
    [accessToken, currentUser, tenantId],
  );

  if (legacyTarget) {
    return <Navigate to={legacyTarget} replace />;
  }

  return (
    <div className="h-full min-h-full overflow-hidden bg-white">
      {loadFailed ? (
        <div className="flex h-full items-center justify-center p-8">
          <Alert
            type="warning"
            showIcon
            title="IAM 子应用未能完成无界挂载"
            description="请先独立访问 IAM 开发服务器确认子应用本身正常。"
            action={
              <Button type="primary" href={url} target="_blank" rel="noreferrer">
                独立打开 IAM
              </Button>
            }
          />
        </div>
      ) : (
        <WujieHost
          width="100%"
          height="100%"
          name={app.name}
          url={url}
          sync={false}
          alive={app.alive}
          fiber={app.fiber}
          degrade={app.degrade}
          prefix={{ [app.name]: app.basename }}
          plugins={app.plugins}
          prepareRestart={refreshSessionFromShell}
          props={props}
          afterMount={() => {
            emitHostNavigate(app, {
              pathname: window.location.pathname,
              search: window.location.search,
              hash: window.location.hash,
            });
          }}
          activated={() => {
            emitHostNavigate(app, {
              pathname: window.location.pathname,
              search: window.location.search,
              hash: window.location.hash,
            });
          }}
          loadError={() => {
            setLoadFailed(true);
          }}
        />
      )}
    </div>
  );
}
