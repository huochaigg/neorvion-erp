import { currentUserQueryKey, ERP_APP_NAME, ERP_BASENAME, ERP_DEFAULT_PATH, type ShellToErpProps } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { fetchCurrentUser } from '@/api/auth';
// import { setupMicroApps } from '@/micro/setup';
import { WujieHost } from '@/micro/wujie-host';
import { useAuthStore } from '@/stores/auth-store';
import { useShellStore } from '@/stores/shell-store';

function getErpEntry() {
  return (import.meta.env.VITE_ERP_ENTRY || 'http://localhost:8016').replace(/\/$/, '');
}

/** 主应用 /erp/dashboard → 子应用 http://localhost:8016/dashboard，禁止拼出 /erp/erp。 */
function buildErpUrl(pathname: string) {
  const entry = getErpEntry();
  if (pathname === ERP_BASENAME || pathname === `${ERP_BASENAME}/`) {
    return `${entry}${ERP_DEFAULT_PATH}`;
  }
  if (pathname.startsWith(`${ERP_BASENAME}/`)) {
    return `${entry}${pathname.slice(ERP_BASENAME.length)}`;
  }
  return `${entry}${ERP_DEFAULT_PATH}`;
}

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

  const url = buildErpUrl(location.pathname);

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
          name={ERP_APP_NAME}
          url={url}
          sync
          alive={false}
          prefix={{ [ERP_APP_NAME]: ERP_BASENAME }}
          props={props}
          fiber={false}
          degrade={false}
          loadError={(err) => {
            console.log('loadError', err)
            setLoadFailed(true)
          }}
        />
      )}
    </div>
  );
}
