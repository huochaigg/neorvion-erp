import { StrictMode } from 'react'; import { createRoot, type Root } from 'react-dom/client'; import { App } from './App'; import './index.css';
let root:Root|null=null; function mount(){const el=document.getElementById('root');if(!el)throw new Error('未找到 #root');root??=createRoot(el);root.render(<StrictMode><App/></StrictMode>)} function unmount(){root?.unmount();root=null}
if(window.__POWERED_BY_WUJIE__){window.__WUJIE_MOUNT=mount;window.__WUJIE_UNMOUNT=unmount;window.__WUJIE?.mount()}else mount();
