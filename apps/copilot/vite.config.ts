import path from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
const rootDir = fileURLToPath(new URL('.', import.meta.url));
const origin = 'http://localhost:8019';
const publicBase = process.env.VITE_PUBLIC_BASE || '/';
export default defineConfig(({command})=>({plugins:[react(),tailwindcss(),{name:'absolute-dev-origin',transformIndexHtml(html){return command==='serve'?html.replaceAll('src="/',`src="${origin}/`).replaceAll('href="/',`href="${origin}/`).replaceAll('from "/',`from "${origin}/`):html;}}],base:publicBase,resolve:{alias:{'@':path.resolve(rootDir,'src')}},server:{host:'0.0.0.0',port:8019,strictPort:true,origin,cors:{origin:true,credentials:true}},preview:{host:'0.0.0.0',port:4176,cors:true,headers:{'Access-Control-Allow-Origin':'*'}}}));
