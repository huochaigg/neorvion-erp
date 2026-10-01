import { App } from 'antd';
import { useEffect } from 'react';

type SessionNotice = {
  warning: (config: { content: string; key?: string }) => void;
};

let messageApi: SessionNotice | null = null;

export function registerSessionNotice(api: SessionNotice | null) {
  messageApi = api;
}

export function warnSessionExpired(content: string) {
  messageApi?.warning({ content, key: 'session-expired' });
}

/** 把 Antd App 的 message 交给拦截器使用，保证挂到主应用而不是 ERP 影子 DOM。 */
export function AntdMessageBridge() {
  const { message } = App.useApp();
  useEffect(() => {
    registerSessionNotice(message);
    return () => registerSessionNotice(null);
  }, [message]);
  return null;
}
