import { ERP_DEFAULT_PATH } from '@neorvion/shared';
import { Spin } from 'antd';
import { Suspense } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { ErpLayout } from '@/layouts/ErpLayout';
import { TenantChangeBridge } from '@/micro/TenantChangeBridge';
import { WujieRouteBridge } from '@/micro/WujieRouteBridge';
import { buildRouteElements } from '@/router/build-routes';
import { PAGE_COMPONENTS } from '@/router/pages';
import { useErpTenantStore } from '@/stores/tenant-runtime';

function LayoutFrame() {
  const epoch = useErpTenantStore((state) => state.epoch);
  return (
    <ErpLayout>
      <div key={epoch}>
        <Outlet />
      </div>
    </ErpLayout>
  );
}

function NotFoundPage() {
  const Page = PAGE_COMPONENTS.Placeholder;
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[240px] items-center justify-center">
          <Spin />
        </div>
      }
    >
      <Page title="未找到页面" description={`可返回 ${ERP_DEFAULT_PATH}`} />
    </Suspense>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <WujieRouteBridge />
      <TenantChangeBridge />
      <Routes>
        <Route element={<LayoutFrame />}>
          <Route index element={<Navigate to={ERP_DEFAULT_PATH} replace />} />
          {buildRouteElements()}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
