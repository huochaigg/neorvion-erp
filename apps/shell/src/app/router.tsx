import { COPILOT_BASENAME, ERP_BASENAME, IAM_BASENAME, KNOWLEDGE_BASENAME, SHELL_ROUTES } from '@neorvion/shared';
import { BrowserRouter, Outlet, Route, Routes } from 'react-router-dom';
import { AuthBootstrap } from '@/components/AuthBootstrap';
import { GuestOnly } from '@/components/GuestOnly';
import { RequireAuth } from '@/components/RequireAuth';
import { RequirePasswordChange } from '@/components/RequirePasswordChange';
import { RequireTenant } from '@/components/RequireTenant';
import { TenantBootstrap } from '@/components/TenantBootstrap';
import { ShellLayout } from '@/layouts/ShellLayout';
import { ErpMicroApp } from '@/micro/ErpMicroApp';
import { IamMicroApp } from '@/micro/IamMicroApp';
import { KnowledgeMicroApp } from '@/micro/KnowledgeMicroApp';
import { CopilotMicroApp } from '@/micro/CopilotMicroApp';
import { CopilotIndexRedirect, ErpIndexRedirect, IamIndexRedirect, KnowledgeIndexRedirect } from '@/micro/MicroAppIndexRedirect';
import { ChangePasswordPage } from '@/pages/ChangePasswordPage';
import { CreateWorkspacePage } from '@/pages/CreateWorkspacePage';
import { HomePage } from '@/pages/HomePage';
import { LoginPage } from '@/pages/LoginPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { WorkspacesPage } from '@/pages/WorkspacesPage';

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
                <RequirePasswordChange />
              </RequireAuth>
            }
          >
            <Route path={SHELL_ROUTES.changePassword} element={<ChangePasswordPage />} />
            <Route
              element={
                <TenantBootstrap>
                  <AppShell />
                </TenantBootstrap>
              }
            >
              <Route path={SHELL_ROUTES.workspaces} element={<WorkspacesPage />} />
              <Route path={SHELL_ROUTES.workspaceCreate} element={<CreateWorkspacePage />} />
              <Route
                element={
                  <RequireTenant>
                    <Outlet />
                  </RequireTenant>
                }
              >
                <Route path={SHELL_ROUTES.home} element={<HomePage />} />
                <Route path={ERP_BASENAME} element={<ErpIndexRedirect />} />
                <Route path={`${ERP_BASENAME}/`} element={<ErpIndexRedirect />} />
                <Route path={`${ERP_BASENAME}/*`} element={<ErpMicroApp />} />
                <Route path={KNOWLEDGE_BASENAME} element={<KnowledgeIndexRedirect />} />
                <Route path={`${KNOWLEDGE_BASENAME}/`} element={<KnowledgeIndexRedirect />} />
                <Route path={`${KNOWLEDGE_BASENAME}/*`} element={<KnowledgeMicroApp />} />
                <Route path={COPILOT_BASENAME} element={<CopilotIndexRedirect />} />
                <Route path={`${COPILOT_BASENAME}/`} element={<CopilotIndexRedirect />} />
                <Route path={`${COPILOT_BASENAME}/*`} element={<CopilotMicroApp />} />
                <Route path={IAM_BASENAME} element={<IamIndexRedirect />} />
                <Route path={`${IAM_BASENAME}/`} element={<IamIndexRedirect />} />
                <Route path={`${IAM_BASENAME}/*`} element={<IamMicroApp />} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </AuthBootstrap>
    </BrowserRouter>
  );
}
