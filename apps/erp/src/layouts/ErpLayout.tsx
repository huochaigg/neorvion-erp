import {
  AppstoreOutlined,
  DatabaseOutlined,
  HomeOutlined,
  ShoppingCartOutlined,
  ShopOutlined,
} from '@ant-design/icons';
import { ERP_ROUTES } from '@neorvion/shared';
import { Layout, Menu, Tag } from 'antd';
import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { isEmbeddedInWujie } from '@/lib/runtime';
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

  const selectedKey = location.pathname.startsWith('/erp')
    ? location.pathname
    : ERP_ROUTES.dashboard;

  const menuItems = useMemo(
    () => [
      { key: ERP_ROUTES.dashboard, icon: <HomeOutlined />, label: '工作台' },
      { key: ERP_ROUTES.products, icon: <AppstoreOutlined />, label: '商品' },
      { key: ERP_ROUTES.warehouses, icon: <ShopOutlined />, label: '仓库' },
      { key: ERP_ROUTES.inventory, icon: <DatabaseOutlined />, label: '库存' },
      { key: ERP_ROUTES.orders, icon: <ShoppingCartOutlined />, label: '订单' },
    ],
    [],
  );

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
            selectedKeys={[selectedKey]}
            items={menuItems}
            className="border-none pt-3"
            onClick={({ key }) => navigate(key)}
          />
        </Sider>
        <Content className="min-w-0 overflow-auto p-5">{children}</Content>
      </Layout>
    </Layout>
  );
}
