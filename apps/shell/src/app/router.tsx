import { ERP_BASENAME, SHELL_ROUTES } from '@neorvion/shared';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { ShellLayout } from '@/layouts/ShellLayout';
import { ErpMicroApp } from '@/micro/ErpMicroApp';
import { HomePage } from '@/pages/HomePage';
import { NotFoundPage } from '@/pages/NotFoundPage';

function AppShell() {
  return (
    <ShellLayout>
      <Outlet />
    </ShellLayout>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path={SHELL_ROUTES.home} element={<HomePage />} />
          <Route path={ERP_BASENAME} element={<Navigate to={`${ERP_BASENAME}/dashboard`} replace />} />
          <Route path={`${ERP_BASENAME}/*`} element={<ErpMicroApp />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
