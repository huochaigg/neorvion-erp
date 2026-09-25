import { ERP_ROUTES } from '@neorvion/shared';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { ErpLayout } from '@/layouts/ErpLayout';
import { DashboardPage } from '@/pages/DashboardPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';

function LayoutFrame() {
  return (
    <ErpLayout>
      <Outlet />
    </ErpLayout>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to={ERP_ROUTES.dashboard} replace />} />
        <Route path="/erp" element={<LayoutFrame />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route
            path="products"
            element={
              <PlaceholderPage title="商品管理" description="M3 将实现 SPU / SKU、编码与状态筛选。" />
            }
          />
          <Route
            path="warehouses"
            element={
              <PlaceholderPage title="仓库管理" description="M3 将实现仓库启停与库存查询。" />
            }
          />
          <Route
            path="inventory"
            element={
              <PlaceholderPage
                title="库存管理"
                description="M3 将实现实际库存、预占库存与库存流水。"
              />
            }
          />
          <Route
            path="orders"
            element={
              <PlaceholderPage title="销售订单" description="M5 将实现审核、预占、出库与发货。" />
            }
          />
          <Route
            path="*"
            element={
              <PlaceholderPage title="未找到页面" description={`可返回 ${ERP_ROUTES.dashboard}`} />
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
