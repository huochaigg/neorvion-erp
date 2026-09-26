/** 带资源 ID 的详情/编辑页不能跨租户沿用，切租户后回到模块列表。 */
const RESOURCE_FALLBACKS: ReadonlyArray<{ pattern: RegExp; fallback: string }> = [
  { pattern: /^\/products\/\d+(\/edit)?\/?$/, fallback: '/products/list' },
  { pattern: /^\/orders\/\d+(\/.*)?$/, fallback: '/orders' },
  { pattern: /^\/inventory\/\d+(\/.*)?$/, fallback: '/inventory/list' },
];

export function safePathAfterTenantChange(pathname: string): string | null {
  const match = RESOURCE_FALLBACKS.find((item) => item.pattern.test(pathname));
  return match ? match.fallback : null;
}
