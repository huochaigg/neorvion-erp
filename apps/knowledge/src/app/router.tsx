import { KNOWLEDGE_DEFAULT_PATH } from '@neorvion/shared';
import { Spin } from 'antd';
import { Suspense } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { PermissionGuard } from '@/components/PermissionGuard';
import { KnowledgeLayout } from '@/layouts/KnowledgeLayout';
import { TenantChangeBridge } from '@/micro/TenantChangeBridge';
import { WujieRouteBridge } from '@/micro/WujieRouteBridge';
import { DocumentDetailPage } from '@/pages/DocumentDetailPage';
import { KnowledgeBaseDetailPage } from '@/pages/KnowledgeBaseDetailPage';
import { KnowledgeBaseListPage } from '@/pages/KnowledgeBaseListPage';
import { TaskListPage } from '@/pages/TaskListPage';
import { WorkbenchPage } from '@/pages/WorkbenchPage';
import { useKnowledgeTenantStore } from '@/stores/tenant-runtime';

function LayoutFrame() {
  const epoch = useKnowledgeTenantStore((state) => state.epoch);
  return (
    <KnowledgeLayout>
      <div key={epoch} className="flex h-full min-h-0 flex-col">
        <PermissionGuard>
          <Outlet />
        </PermissionGuard>
      </div>
    </KnowledgeLayout>
  );
}

function NotFoundPage() {
  return (
    <div className="flex min-h-[240px] items-center justify-center text-slate-500">
      未找到页面，可返回工作台
    </div>
  );
}

function Fallback() {
  return (
    <div className="flex min-h-[240px] items-center justify-center">
      <Spin />
    </div>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <WujieRouteBridge />
      <TenantChangeBridge />
      <Routes>
        <Route element={<LayoutFrame />}>
          <Route index element={<Navigate to={KNOWLEDGE_DEFAULT_PATH} replace />} />
          <Route
            path="/workbench"
            element={
              <Suspense fallback={<Fallback />}>
                <WorkbenchPage />
              </Suspense>
            }
          />
          <Route
            path="/bases"
            element={
              <Suspense fallback={<Fallback />}>
                <KnowledgeBaseListPage />
              </Suspense>
            }
          />
          <Route
            path="/bases/:id"
            element={
              <Suspense fallback={<Fallback />}>
                <KnowledgeBaseDetailPage />
              </Suspense>
            }
          />
          <Route
            path="/bases/:id/documents/:docId"
            element={
              <Suspense fallback={<Fallback />}>
                <DocumentDetailPage />
              </Suspense>
            }
          />
          <Route
            path="/tasks"
            element={
              <Suspense fallback={<Fallback />}>
                <TaskListPage />
              </Suspense>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
