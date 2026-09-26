import { ERP_DEFAULT_PATH } from '@neorvion/shared';
import { Spin } from 'antd';
import { Suspense } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { ErpLayout } from '@/layouts/ErpLayout';
import { WujieRouteBridge } from '@/micro/WujieRouteBridge';
import { buildRouteElements } from '@/router/build-routes';
import { PAGE_COMPONENTS } from '@/router/pages';

function LayoutFrame() {
  return (
    <ErpLayout>
      <Outlet />
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
