import {
  AppstoreOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { ERP_ROUTES, SHELL_ROUTES } from '@neorvion/shared';
import { Avatar, Button, Layout, Menu, Space, Tag } from 'antd';
import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppLogo } from '@/components/AppLogo';
import { useShellStore } from '@/stores/shell-store';

const { Header, Sider, Content } = Layout;

interface ShellLayoutProps {
  children: ReactNode;
}

export function ShellLayout({ children }: ShellLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const siderCollapsed = useShellStore((state) => state.siderCollapsed);
  const toggleSider = useShellStore((state) => state.toggleSider);

  const selectedKey = location.pathname.startsWith(SHELL_ROUTES.erp)
    ? SHELL_ROUTES.erp
    : SHELL_ROUTES.home;

  const menuItems = useMemo(
    () => [
      { key: SHELL_ROUTES.home, icon: <AppstoreOutlined />, label: '工作台' },
      { key: SHELL_ROUTES.erp, icon: <TeamOutlined />, label: 'ERP 业务' },
    ],
    [],
  );

  return (
    <Layout className="min-h-screen">
      <Header className="flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <AppLogo compact={siderCollapsed} />
          <Tag color="processing">M1 基础设施</Tag>
        </div>
        <Space size={12}>
          <span className="text-sm text-white/70">租户：尚未接入（M2）</span>
          <Avatar size={32} icon={<UserOutlined />} />
        </Space>
      </Header>
      <Layout className="h-[calc(100vh-56px)]">
        <Sider
          collapsible
          collapsed={siderCollapsed}
          trigger={null}
          width={220}
          className="border-r border-slate-200"
        >
          <div className="flex h-full flex-col">
            <Menu
              mode="inline"
              selectedKeys={[selectedKey]}
              items={menuItems}
              className="flex-1 border-none pt-2"
              onClick={({ key }) => {
                if (key === SHELL_ROUTES.erp) {
                  navigate(ERP_ROUTES.dashboard);
                  return;
                }
                navigate(key);
              }}
            />
            <div className="border-t border-slate-100 p-2">
              <Button
                type="text"
                block
                icon={siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={toggleSider}
              >
                {siderCollapsed ? '' : '收起菜单'}
              </Button>
            </div>
          </div>
        </Sider>
        <Content className="h-full min-h-0 min-w-0 overflow-hidden">{children}</Content>
      </Layout>
    </Layout>
  );
}
