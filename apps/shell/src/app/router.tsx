import { ERP_BASENAME, ERP_DEFAULT_PATH, SHELL_ROUTES } from '@neorvion/shared';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { AuthBootstrap } from '@/components/AuthBootstrap';
import { GuestOnly } from '@/components/GuestOnly';
import { RequireAuth } from '@/components/RequireAuth';
import { ShellLayout } from '@/layouts/ShellLayout';
import { ErpMicroApp } from '@/micro/ErpMicroApp';
import { HomePage } from '@/pages/HomePage';
import { LoginPage } from '@/pages/LoginPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { RegisterPage } from '@/pages/RegisterPage';

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
      <AuthBootstrap>
        <Routes>
          <Route
            path={SHELL_ROUTES.login}
            element={
              <GuestOnly>
                <LoginPage />
              </GuestOnly>
            }
          />
          <Route
            path={SHELL_ROUTES.register}
            element={
              <GuestOnly>
                <RegisterPage />
              </GuestOnly>
            }
          />
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path={SHELL_ROUTES.home} element={<HomePage />} />
            <Route
              path={ERP_BASENAME}
              element={<Navigate to={`${ERP_BASENAME}${ERP_DEFAULT_PATH}`} replace />}
            />
            <Route
              path={`${ERP_BASENAME}/`}
              element={<Navigate to={`${ERP_BASENAME}${ERP_DEFAULT_PATH}`} replace />}
            />
            <Route path={`${ERP_BASENAME}/*`} element={<ErpMicroApp />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </AuthBootstrap>
    </BrowserRouter>
  );
}
