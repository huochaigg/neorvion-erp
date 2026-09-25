import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import App from './App';
import './index.css';

let root: Root | null = null;

function mountApp() {
  const container = document.getElementById('root');
  if (!container) {
    throw new Error('未找到 #root 挂载节点');
  }
  if (!root) {
    root = createRoot(container);
  }
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

function unmountApp() {
  root?.unmount();
  root = null;
}

if (window.__POWERED_BY_WUJIE__) {
  window.__WUJIE_MOUNT = mountApp;
  window.__WUJIE_UNMOUNT = unmountApp;
  // Vite 模块异步加载，必须主动触发无界 mount，避免白屏。
  window.__WUJIE.mount();
} else {
  mountApp();
}
