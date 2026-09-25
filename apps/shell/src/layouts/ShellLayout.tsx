import {
  AppstoreOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { currentUserQueryKey, ERP_BASENAME, ERP_DEFAULT_PATH, SHELL_ROUTES } from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Avatar, Button, Dropdown, Layout, Menu, Space, Tag } from 'antd';
import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { fetchCurrentUser, logoutAccount } from '@/api/auth';
import { AppLogo } from '@/components/AppLogo';
import { useAuthStore } from '@/stores/auth-store';
import { useShellStore } from '@/stores/shell-store';

const { Header, Sider, Content } = Layout;

interface ShellLayoutProps {
  children: ReactNode;
}

export function ShellLayout({ children }: ShellLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const siderCollapsed = useShellStore((state) => state.siderCollapsed);
  const toggleSider = useShellStore((state) => state.toggleSider);
  const accessToken = useAuthStore((state) => state.accessToken);
  const resetAuth = useAuthStore((state) => state.reset);

  const { data: currentUser } = useQuery({
    queryKey: currentUserQueryKey(),
    queryFn: fetchCurrentUser,
    enabled: Boolean(accessToken),
  });

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

  const onLogout = async () => {
    try {
      await logoutAccount();
    } finally {
      resetAuth();
      queryClient.clear();
      navigate(SHELL_ROUTES.login, { replace: true });
    }
  };

  return (
    <Layout className="min-h-screen">
      <Header className="flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <AppLogo compact={siderCollapsed} />
          <Tag color="processing">V2.1.1</Tag>
        </div>
        <Space size={12}>
          <span className="text-sm text-white/70">租户：尚未接入（V2.2）</span>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  label: '退出登录',
                  onClick: () => {
                    void onLogout();
                  },
                },
              ],
            }}
          >
            <Space className="cursor-pointer text-white">
              <Avatar size={32} icon={<UserOutlined />} />
              <span className="text-sm">{currentUser?.display_name ?? '已登录'}</span>
            </Space>
          </Dropdown>
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
                  navigate(`${ERP_BASENAME}${ERP_DEFAULT_PATH}`);
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
        <Content className="h-full min-h-0 min-w-0 overflow-auto">{children}</Content>
      </Layout>
    </Layout>
  );
}
