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
