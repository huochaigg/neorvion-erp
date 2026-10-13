import { KNOWLEDGE_DEFAULT_PATH } from '../constants/routes';

/** Knowledge 详情页不能跨租户沿用，切租户后回到模块安全首页。 */
export function safeKnowledgePathAfterTenantChange(pathname: string): string | null {
  if (/^\/bases\/[^/]+(\/.*)?\/?$/.test(pathname)) {
    return KNOWLEDGE_DEFAULT_PATH;
  }
  if (/^\/chat\/[^/]+\/?$/.test(pathname)) {
    return '/chat';
  }
  if (/^\/tasks\/[^/]+\/?$/.test(pathname)) {
    return '/tasks';
  }
  if (/^\/datasets\/[^/]+\/?$/.test(pathname)) {
    return '/datasets';
  }
  if (/^\/experiments\/\d+\/?$/.test(pathname)) {
    return '/experiments';
  }
  return null;
}
