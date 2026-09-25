import { ApiError } from '@neorvion/shared';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { useTenantQuerySync } from '@/hooks/use-tenant-query-sync';

const theme = {
  token: {
    colorPrimary: '#0f4c81',
    borderRadius: 6,
    fontFamily: 'inherit',
  },
  components: {
    Layout: {
      headerBg: '#0f2744',
      headerHeight: 56,
      bodyBg: '#f3f5f8',
      siderBg: '#ffffff',
    },
  },
};

function getPopupContainer(node?: HTMLElement) {
  if (node) {
    const overlayRoot = node.closest('#root');
    if (overlayRoot instanceof HTMLElement) {
      return overlayRoot;
    }
  }
  return document.getElementById('root') ?? document.body;
}

interface AppProvidersProps {
  children: ReactNode;
}

function TenantAwareQueryLayer({
  queryClient,
  children,
}: {
  queryClient: QueryClient;
  children: ReactNode;
}) {
  useTenantQuerySync(queryClient);
  return children;
}

export function AppProviders({ children }: AppProvidersProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (failureCount, error) => {
              if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
                return false;
              }
              return failureCount < 1;
            },
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN} theme={theme} getPopupContainer={getPopupContainer}>
        <AntdApp>
          <TenantAwareQueryLayer queryClient={queryClient}>{children}</TenantAwareQueryLayer>
        </AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
