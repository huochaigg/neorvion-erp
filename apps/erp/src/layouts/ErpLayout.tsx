import { Layout, Menu, Tag } from 'antd';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppBreadcrumb } from '@/components/AppBreadcrumb';
import { usePermissions } from '@/hooks/usePermissions';
import { isEmbeddedInWujie } from '@/lib/runtime';
import { buildMenuItems } from '@/router/menu';
import { getOpenKeysForPath, getSelectedMenuKey, matchRoute, resolveNavigatePath } from '@/router/match';
import { routes } from '@/router/routes';
import { useErpStore } from '@/stores/erp-store';

const { Header, Sider, Content } = Layout;

interface ErpLayoutProps {
  children: ReactNode;
}

export function ErpLayout({ children }: ErpLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { permissions, isLoading } = usePermissions();
  const siderCollapsed = useErpStore((state) => state.siderCollapsed);
  const setSiderCollapsed = useErpStore((state) => state.setSiderCollapsed);
  const embedded = isEmbeddedInWujie();
  const menuItems = useMemo(
    () => buildMenuItems(routes, isLoading ? [] : permissions),
    [isLoading, permissions],
  );
  const match = useMemo(() => matchRoute(routes, location.pathname), [location.pathname]);
  const selectedKey = getSelectedMenuKey(match);
  const computedOpenKeys = useMemo(
    () => getOpenKeysForPath(routes, location.pathname),
    [location.pathname],
  );
  const [openKeys, setOpenKeys] = useState<string[]>(computedOpenKeys);

  useEffect(() => {
    setOpenKeys(computedOpenKeys);
  }, [computedOpenKeys]);

  return (
    <Layout className="h-full min-h-0 overflow-hidden">
      {embedded ? null : (
        <Header className="flex shrink-0 items-center justify-between px-4">
          <span className="text-sm font-semibold text-white">Neorvion ERP · 独立运行</span>
          <Tag color="gold">开发调试</Tag>
        </Header>
      )}
      <Layout className="min-h-0 flex-1 overflow-hidden">
        <Sider
          collapsible
          collapsed={siderCollapsed}
          onCollapse={setSiderCollapsed}
          width={208}
          className="border-r border-slate-200"
        >
          <Menu
            mode="inline"
            selectedKeys={selectedKey ? [selectedKey] : []}
            openKeys={siderCollapsed ? [] : openKeys}
            onOpenChange={setOpenKeys}
            items={menuItems}
            className="h-full overflow-y-auto border-none pt-3"
            onClick={({ key }) => {
              navigate(resolveNavigatePath(routes, key));
            }}
          />
        </Sider>
        <Content className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden px-5 pb-4 pt-4">
          <div className="shrink-0">
            <AppBreadcrumb pathname={location.pathname} />
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
        </Content>
      </Layout>
    </Layout>
  );
}
