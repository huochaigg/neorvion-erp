import { ApiError } from '@neorvion/shared';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { CopilotPage } from '@/pages/CopilotPage';
import { TenantBridge } from '@/micro/TenantBridge';
import { useCopilotStore } from '@/store';

function TenantWorkspace() {
  const epoch = useCopilotStore((s) => s.epoch);
  return <CopilotPage key={epoch} />;
}

export function App() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (n, e) => !(e instanceof ApiError && [401, 403].includes(e.status)) && n < 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#0f4c81', borderRadius: 6 } }}>
        <AntApp>
          <BrowserRouter>
            <TenantBridge />
            <Routes>
              <Route path="/chat" element={<TenantWorkspace />} />
              <Route path="/" element={<Navigate to="/chat" replace />} />
              <Route path="*" element={<TenantWorkspace />} />
            </Routes>
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
