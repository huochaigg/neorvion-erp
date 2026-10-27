import { ApiError } from '@neorvion/shared';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { isCancel } from 'axios';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { lazy, Suspense, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { WorkbenchLayout } from '@/components/WorkbenchLayout';
import { TenantBridge } from '@/micro/TenantBridge';
import { WujieRouteBridge } from '@/micro/WujieRouteBridge';
import { AdsComingSoonPage, HistoryComingSoonPage } from '@/pages/ComingSoonPage';
import { CopilotPage } from '@/pages/CopilotPage';
import { WorkflowDetailPage } from '@/pages/WorkflowDetailPage';
import { getPopupContainer } from '@/runtime';
import { useCopilotStore } from '@/store';

const InsightCenterPage = lazy(() => import('@/pages/InsightCenterPage'));
const TaskCenterPage = lazy(() => import('@/pages/TaskCenterPage'));
const AIManagementPage = lazy(() => import('@/pages/AIManagementPage'));

function TenantWorkspace() {
  const epoch = useCopilotStore((s) => s.epoch);
  return (
    <Routes>
      <Route element={<WorkbenchLayout key={epoch} />}>
        <Route path="/chat" element={<CopilotPage />} />
        <Route
          path="/tasks"
          element={
            <Suspense fallback={<div className="p-6">正在加载任务工作区…</div>}>
              <TaskCenterPage />
            </Suspense>
          }
        />
        <Route path="/drafts" element={<Navigate to="/tasks?tab=drafts" replace />} />
        <Route path="/approvals" element={<Navigate to="/tasks?tab=pending" replace />} />
        <Route path="/workflows" element={<Navigate to="/tasks?tab=workflows" replace />} />
        <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="/tasks/workflows/:id" element={<WorkflowDetailPage />} />
        <Route
          path="/manage"
          element={
            <Suspense fallback={<div className="p-6">正在加载 AI 管理中心…</div>}>
              <AIManagementPage />
            </Suspense>
          }
        />
        <Route path="/evaluations" element={<Navigate to="/manage" replace />} />
        <Route
          path="/insights"
          element={
            <Suspense fallback={<div className="p-6">正在加载主动洞察…</div>}>
              <InsightCenterPage />
            </Suspense>
          }
        />
        <Route path="/ads" element={<AdsComingSoonPage />} />
        <Route path="/creative-history" element={<HistoryComingSoonPage />} />
        <Route path="/history" element={<Navigate to="/creative-history" replace />} />
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (n, e) =>
              !(e instanceof ApiError && [401, 403].includes(e.status)) && !isCancel(e) && n < 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <ConfigProvider
        locale={zhCN}
        getPopupContainer={getPopupContainer}
        theme={{
          cssVar: { prefix: 'copilot-theme' },
          token: {
            colorPrimary: '#6366F1',
            colorText: '#0F172A',
            colorTextSecondary: '#64748B',
            colorBorder: '#E2E8F0',
            colorBgLayout: '#F8FAFC',
            borderRadius: 14,
            fontFamily: 'inherit',
          },
          components: {
            Button: { primaryShadow: 'none' },
          },
        }}
      >
        <AntApp className="h-full min-h-0 flex-1">
          <BrowserRouter>
            <WujieRouteBridge />
            <TenantBridge />
            <TenantWorkspace />
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
