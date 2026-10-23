import { ApiError } from '@neorvion/shared';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { isCancel } from 'axios';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { WorkbenchLayout } from '@/components/WorkbenchLayout';
import { TenantBridge } from '@/micro/TenantBridge';
import { WujieRouteBridge } from '@/micro/WujieRouteBridge';
import { AdsComingSoonPage, HistoryComingSoonPage } from '@/pages/ComingSoonPage';
import { CopilotPage } from '@/pages/CopilotPage';
import { getPopupContainer } from '@/runtime';
import { useCopilotStore } from '@/store';

function TenantWorkspace() {
  const epoch = useCopilotStore((s) => s.epoch);
  return (
    <Routes>
      <Route element={<WorkbenchLayout key={epoch} />}>
        <Route path="/chat" element={<CopilotPage />} />
        <Route path="/ads" element={<AdsComingSoonPage />} />
        <Route path="/history" element={<HistoryComingSoonPage />} />
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
            retry: (n, e) => !(e instanceof ApiError && [401, 403].includes(e.status)) && !isCancel(e) && n < 1,
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
