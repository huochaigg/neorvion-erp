import { COPILOT_APP_NAME, type ShellToErpProps } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button } from 'antd';
import { useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { fetchCurrentUser } from '@/api/auth';
import { refreshSessionFromShell } from '@/api/client';
import { buildMicroAppUrl, getMicroApp } from '@/micro/apps';
import { consumeLegacyWujieSyncQuery, emitHostNavigate, useMicroHostRouteSync } from '@/micro/route-sync';
import { WujieHost } from '@/micro/wujie-host';
import { useAuthStore } from '@/stores/auth-store';
import { useTenantStore } from '@/stores/tenant-store';

export function CopilotMicroApp() {
  const location = useLocation();
  const tenantId = useTenantStore((state) => state.currentTenantId);
  const token = useAuthStore((state) => state.accessToken);
  const [loadFailed, setLoadFailed] = useState(false);
  const { data: user } = useQuery({ queryKey: ['current-user'], queryFn: fetchCurrentUser, enabled: Boolean(token) });
  const app = getMicroApp(COPILOT_APP_NAME);
  const legacy = consumeLegacyWujieSyncQuery(app, location);
  const url = buildMicroAppUrl(app, location.pathname, location.search, location.hash);
  useMicroHostRouteSync(app);
  const props = useMemo<ShellToErpProps>(
    () => ({
      token,
      tenantId,
      user: user ? { id: user.id, displayName: user.display_name } : null,
      refreshSession: refreshSessionFromShell,
    }),
    [token, tenantId, user],
  );
  if (legacy) {
    return <Navigate to={legacy} replace />;
  }
  return (
    <div className="h-full min-h-full overflow-hidden bg-white">
      {loadFailed ? (
        <div className="flex h-full items-center justify-center p-8">
          <Alert
            type="warning"
            showIcon
            title="Copilot 子应用未能加载"
            description="请确认 apps/copilot 开发服务已在 8019 端口运行，或用系统 Chrome 打开主应用。"
            action={
              <Button type="primary" href={url} target="_blank" rel="noreferrer">
                独立打开 Copilot
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
          props={props}
          prepareRestart={refreshSessionFromShell}
          afterMount={() =>
            emitHostNavigate(app, {
              pathname: window.location.pathname,
              search: window.location.search,
              hash: window.location.hash,
            })
          }
          activated={() =>
            emitHostNavigate(app, {
              pathname: window.location.pathname,
              search: window.location.search,
              hash: window.location.hash,
            })
          }
          loadError={() => {
            setLoadFailed(true);
          }}
        />
      )}
    </div>
  );
}
