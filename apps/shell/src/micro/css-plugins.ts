import type { plugin } from 'wujie';

/**
 * 仅给运行在 Shadow DOM 中的 Tailwind v4 子应用使用。
 * Vue 或其他 CSS 方案不要默认挂这个插件。
 */
export function tailwindV4ShadowCssPlugin(): plugin {
  return {
    cssLoader(code: string) {
      if (!code.includes(':root')) {
        return code;
      }
      return code.replace(/(^|[\s,{>+~|;])(:root)(?=[\s,{:[,]|$])/g, '$1:host');
    },
  };
}

/**
 * 开发态 Vite HTML 里的 /src/main.tsx 是相对路径。
 * 无界 iframe 的 location 是主应用 origin，不改写就会加载到 Shell 自己的脚本。
 */
export function viteDevPublicPathPlugin(getOrigin: () => string): plugin {
  return {
    htmlLoader(code) {
      const origin = getOrigin().replace(/\/$/, '');
      if (!origin) {
        return code;
      }
      return code
        .replace(/(src=["'])\//g, `$1${origin}/`)
        .replace(/(href=["'])\//g, `$1${origin}/`)
        .replace(/(from\s+["'])\//g, `$1${origin}/`);
    },
  };
}
