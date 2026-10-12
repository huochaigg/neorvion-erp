import assert from 'node:assert/strict';
import {
  ANALYTICS_STALE_TIME_MS,
  analyticsQueryKey,
  formatAnalyticsAmount,
  formatAnalyticsRate,
  PERMISSION_CODE,
  toChartNumber,
} from '@neorvion/shared';
import { describe, it } from 'vitest';
import { filterMenuRoutes, pageAllowsAccess } from '@/router/access';
import { matchRoute } from '@/router/match';
import { routes } from '@/router/routes';

function menuPaths(items: ReturnType<typeof filterMenuRoutes>): string[] {
  const paths: string[] = [];
  const walk = (list: typeof items) => {
    for (const item of list) {
      paths.push(item.path);
      if (item.children?.length) {
        walk(item.children);
      }
    }
  };
  walk(items);
  return paths;
}

describe('数据中心 UI 规则', () => {
  it('Query Key 含 tenant 和筛选，金额与比率由后端字段格式化', () => {
    assert.notDeepEqual(
      analyticsQueryKey(1, 'sales-summary', { startDate: '2026-10-01' }),
      analyticsQueryKey(2, 'sales-summary', { startDate: '2026-10-01' }),
    );
    assert.equal(ANALYTICS_STALE_TIME_MS, 30_000);
    assert.equal(formatAnalyticsAmount(12000), '12,000.00');
    assert.equal(formatAnalyticsRate(0.5), '50.00%');
    assert.equal(toChartNumber('12.5'), 12.5);
    assert.equal(toChartNumber(null), 0);
  });

  it('菜单与页面权限和后端 analytics:*:read 一致', () => {
    const salesOnly = [PERMISSION_CODE.analyticsSalesRead];
    const paths = menuPaths(filterMenuRoutes(routes, salesOnly));
    assert.equal(paths.includes('/analytics'), true);
    assert.equal(paths.includes('/analytics/sales'), true);
    assert.equal(paths.includes('/analytics/purchases'), false);
    assert.equal(paths.includes('/analytics/inventory'), false);
    const salesMatch = matchRoute(routes, '/analytics/sales');
    assert.equal(pageAllowsAccess(salesMatch, []), false);
    assert.equal(pageAllowsAccess(salesMatch, [PERMISSION_CODE.analyticsSalesRead]), true);
    const purchaseMatch = matchRoute(routes, '/analytics/purchases');
    assert.equal(pageAllowsAccess(purchaseMatch, [PERMISSION_CODE.analyticsSalesRead]), false);
    assert.equal(pageAllowsAccess(purchaseMatch, [PERMISSION_CODE.analyticsPurchaseRead]), true);
    const inventoryMatch = matchRoute(routes, '/analytics/inventory');
    assert.equal(pageAllowsAccess(inventoryMatch, [PERMISSION_CODE.analyticsInventoryRead]), true);
    const afterMatch = matchRoute(routes, '/analytics/after-sales');
    assert.equal(pageAllowsAccess(afterMatch, [PERMISSION_CODE.analyticsAfterSaleRead]), true);
    const dashboard = matchRoute(routes, '/dashboard');
    assert.equal(pageAllowsAccess(dashboard, []), true);
  });
});
