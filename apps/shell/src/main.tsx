import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { setupMicroApps } from './micro/setup';
import App from './App';
import './index.css';


const container = document.getElementById('root');
if (!container) {
  throw new Error('未找到 #root 挂载节点');
}

// 注册配置，不启动或预加载 ERP
setupMicroApps();

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
