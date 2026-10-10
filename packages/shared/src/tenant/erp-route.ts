/** 带资源 ID 的详情/编辑页不能跨租户沿用，切租户后回到模块列表。 */
const RESOURCE_FALLBACKS: ReadonlyArray<{ pattern: RegExp; fallback: string }> = [
  { pattern: /^\/products\/\d+(\/edit)?\/?$/, fallback: '/products/list' },
  { pattern: /^\/orders\/\d+(\/edit)?\/?$/, fallback: '/orders/list' },
  { pattern: /^\/inventory\/\d+(\/.*)?$/, fallback: '/inventory/list' },
  { pattern: /^\/purchases\/\d+(\/edit)?\/?$/, fallback: '/purchases/list' },
  { pattern: /^\/purchase-receipts\/\d+\/?$/, fallback: '/purchase-receipts' },
  { pattern: /^\/outbound-orders\/\d+\/?$/, fallback: '/outbound-orders' },
  { pattern: /^\/shipments\/\d+\/?$/, fallback: '/shipments' },
  { pattern: /^\/stocktakes\/\d+\/?$/, fallback: '/stocktakes' },
  { pattern: /^\/stock-transfers\/\d+(\/edit)?\/?$/, fallback: '/stock-transfers' },
  { pattern: /^\/system\/members\/\d+\/?$/, fallback: '/system/members' },
];

export function safePathAfterTenantChange(pathname: string): string | null {
  const match = RESOURCE_FALLBACKS.find((item) => item.pattern.test(pathname));
  return match ? match.fallback : null;
}
