import { currentUserQueryKey, ERP_APP_NAME, type ShellToErpProps } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button } from 'antd';
import { useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { fetchCurrentUser } from '@/api/auth';
import { buildMicroAppUrl, getMicroApp } from '@/micro/apps';
import { consumeLegacyWujieSyncQuery, emitHostNavigate, useMicroHostRouteSync } from '@/micro/route-sync';
import { WujieHost } from '@/micro/wujie-host';
import { useAuthStore } from '@/stores/auth-store';
import { useShellStore } from '@/stores/shell-store';

export function ErpMicroApp() {
  const location = useLocation();
  const tenantId = useShellStore((state) => state.currentTenantId);
  const accessToken = useAuthStore((state) => state.accessToken);
  const [loadFailed, setLoadFailed] = useState(false);
  const { data: currentUser } = useQuery({
    queryKey: currentUserQueryKey(),
    queryFn: fetchCurrentUser,
    enabled: Boolean(accessToken),
  });

  const app = getMicroApp(ERP_APP_NAME);
  const legacyTarget = consumeLegacyWujieSyncQuery(app, location);
  const url = buildMicroAppUrl(app, location.pathname, location.search, location.hash);

  useMicroHostRouteSync(app);

  const props = useMemo<ShellToErpProps>(
    () => ({
      token: accessToken,
      tenantId,
      user: currentUser
        ? { id: currentUser.id, displayName: currentUser.display_name }
        : null,
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
            title="ERP 子应用未能在当前浏览器沙箱中完成无界挂载"
            description="请用系统 Chrome 打开主应用，或先独立访问 ERP 开发服务器确认子应用本身正常。"
            action={
              <Button type="primary" href={url} target="_blank" rel="noreferrer">
                独立打开 ERP
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
