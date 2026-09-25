import { ERP_APP_NAME, ERP_ROUTES, type ShellToErpProps } from '@neorvion/shared';
import { Alert, Button } from 'antd';
import { useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { WujieHost } from '@/micro/wujie-host';
import { useShellStore } from '@/stores/shell-store';

function buildErpUrl(pathname: string) {
  const entry = import.meta.env.VITE_ERP_ENTRY.replace(/\/$/, '');
  const normalizedPath = pathname.startsWith('/erp') ? pathname : ERP_ROUTES.dashboard;
  return `${entry}${normalizedPath}`;
}

export function ErpMicroApp() {
  const location = useLocation();
  const tenantId = useShellStore((state) => state.currentTenantId);
  const [loadFailed, setLoadFailed] = useState(false);

  const url = buildErpUrl(location.pathname);

  const props = useMemo<ShellToErpProps>(
    () => ({
      token: null,
      tenantId,
      user: null,
    }),
    [tenantId],
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
          props={props}
          fiber={false}
          loadError={() => setLoadFailed(true)}
        />
      )}
    </div>
  );
}
