import { ApiError } from '@neorvion/shared';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import { useState, type ReactNode } from 'react';
import { getPopupContainer } from '@/lib/runtime';

dayjs.locale('zh-cn');

const theme = {
  token: {
    colorPrimary: '#0f4c81',
    colorPrimaryHover: '#1a5f9a',
    colorPrimaryActive: '#0b3c66',
    colorLink: '#0f4c81',
    colorInfo: '#0f4c81',
    colorError: '#c53030',
    borderRadius: 6,
    controlHeight: 32,
    fontFamily: 'inherit',
  },
  components: {
    Layout: {
      headerBg: '#102a43',
      siderBg: '#ffffff',
      bodyBg: '#f3f5f8',
    },
    Menu: {
      itemSelectedBg: '#e8f1f8',
      itemSelectedColor: '#0f4c81',
    },
    Button: {
      primaryShadow: 'none',
    },
  },
};

interface AppProvidersProps {
  children: ReactNode;
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
        <AntdApp>{children}</AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
