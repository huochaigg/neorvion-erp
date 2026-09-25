import { Layout, Menu, Tag } from 'antd';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppBreadcrumb } from '@/components/AppBreadcrumb';
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
  const siderCollapsed = useErpStore((state) => state.siderCollapsed);
  const setSiderCollapsed = useErpStore((state) => state.setSiderCollapsed);
  const embedded = isEmbeddedInWujie();
  const menuItems = useMemo(() => buildMenuItems(routes), []);
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
    <Layout className="h-full min-h-full">
      {embedded ? null : (
        <Header className="flex items-center justify-between px-4">
          <span className="text-sm font-semibold text-white">Neorvion ERP · 独立运行</span>
          <Tag color="gold">开发调试</Tag>
        </Header>
      )}
      <Layout className="h-full min-h-0">
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
            className="border-none pt-3"
            onClick={({ key }) => {
              navigate(resolveNavigatePath(routes, key));
            }}
          />
        </Sider>
        <Content className="min-w-0 overflow-auto p-5">
          <AppBreadcrumb pathname={location.pathname} />
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}
