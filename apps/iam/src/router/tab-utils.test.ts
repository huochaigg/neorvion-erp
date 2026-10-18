import assert from 'node:assert/strict';
import { PERMISSION_CODE } from '@neorvion/shared';
import { describe, it } from 'vitest';
import { routes } from './routes';
import {
  MAX_TABS,
  closeAllTabs,
  closeOtherTabs,
  closeTab,
  closeTabsToTheRight,
  createInitialTabsState,
  createPinnedDashboardTab,
  ensureTab,
  enforceMaxTabs,
  isTabEligiblePath,
  normalizeTabPath,
  pruneInvalidTabs,
  reorderTabs,
  resetTabsForTenant,
  setTabTitle,
  shouldSkipTabAfterTenantChange,
  tabFromPath,
} from './tab-utils';

function visit(path: string, tenantId: number | null = 1) {
  let state = createInitialTabsState(tenantId);
  state = ensureTab(state, path, routes);
  return state;
}

describe('ERP TabBar 路径与唯一性', () => {
  it('忽略 query，列表分页不会制造多个 Tab', () => {
    assert.equal(normalizeTabPath('/orders/list', '?page=1'), '/orders/list');
    assert.equal(normalizeTabPath('/orders/list?page=2'), '/orders/list');
    assert.equal(normalizeTabPath('/orders/list/'), '/orders/list');
    let state = visit('/orders/list?page=1');
    state = ensureTab(state, '/orders/list?page=2', routes);
    assert.equal(state.tabs.filter((item) => item.path === '/orders/list').length, 1);
    assert.equal(state.activeKey, '/orders/list');
  });

  it('动态详情页按完整 path 区分，不按 route.name', () => {
    let state = visit('/orders/123');
    state = ensureTab(state, '/orders/456', routes);
    const keys = state.tabs.map((item) => item.key);
    assert.equal(keys.includes('/orders/123'), true);
    assert.equal(keys.includes('/orders/456'), true);
    assert.equal(state.tabs.filter((item) => item.title === '销售订单详情').length, 2);
  });

  it('重复访问同一路由只激活，不重复创建', () => {
    let state = visit('/products/list');
    state = ensureTab(state, '/products/list', routes);
    state = ensureTab(state, '/products/list', routes);
    assert.equal(state.tabs.filter((item) => item.key === '/products/list').length, 1);
    assert.equal(state.activeKey, '/products/list');
  });

  it('重定向分组路由不入 Tab，正式叶子路由才入', () => {
    assert.equal(isTabEligiblePath('/orders', routes), false);
    assert.equal(isTabEligiblePath('/products', routes), false);
    assert.equal(isTabEligiblePath('/unknown', routes), false);
    assert.equal(isTabEligiblePath('/login', routes), false);
    const skipped = ensureTab(createInitialTabsState(1), '/orders', routes);
    assert.deepEqual(
      skipped.tabs.map((item) => item.key),
      ['/dashboard'],
    );
    const opened = ensureTab(skipped, '/orders/list', routes);
    assert.equal(opened.tabs.some((item) => item.key === '/orders/list'), true);
    assert.equal(opened.tabs.find((item) => item.key === '/orders/list')?.title, '销售订单');
  });

  it('商品列表与工作台标题来自 routes metadata', () => {
    assert.equal(tabFromPath('/dashboard', routes)?.title, '工作台');
    assert.equal(tabFromPath('/products/list', routes)?.title, '商品列表');
    assert.equal(tabFromPath('/products/list', routes)?.closable, true);
    assert.equal(tabFromPath('/dashboard', routes)?.closable, false);
  });
});

describe('ERP TabBar 关闭与上限', () => {
  it('Dashboard 固定且不可关闭，关闭全部仍保留工作台', () => {
    let state = visit('/products/list');
    state = ensureTab(state, '/orders/list', routes);
    state = closeTab(state, '/dashboard');
    assert.equal(state.tabs.some((item) => item.key === '/dashboard'), true);
    state = closeAllTabs(state);
    assert.deepEqual(
      state.tabs.map((item) => item.key),
      ['/dashboard'],
    );
    assert.equal(state.activeKey, '/dashboard');
    assert.equal(createPinnedDashboardTab().closable, false);
  });

  it('关闭非当前 Tab 不改 active；关闭当前切左侧，左侧没有则切右侧', () => {
    let state = createInitialTabsState(1);
    state = ensureTab(state, '/products/list', routes);
    state = ensureTab(state, '/orders/list', routes);
    state = ensureTab(state, '/customers', routes);
    const idle = closeTab(state, '/products/list');
    assert.equal(idle.activeKey, '/customers');
    assert.equal(idle.tabs.some((item) => item.key === '/products/list'), false);
    const closedActive = closeTab(state, '/customers');
    assert.equal(closedActive.activeKey, '/orders/list');
    let onlyRight = createInitialTabsState(1);
    onlyRight = ensureTab(onlyRight, '/orders/list', routes);
    onlyRight = closeTab(onlyRight, '/orders/list');
    assert.equal(onlyRight.activeKey, '/dashboard');
  });

  it('关闭右侧只去掉目标右侧的可关闭 Tab，工作台保留', () => {
    let state = createInitialTabsState(1);
    state = ensureTab(state, '/products/list', routes);
    state = ensureTab(state, '/orders/list', routes);
    state = ensureTab(state, '/customers', routes);
    const closed = closeTabsToTheRight(state, '/orders/list');
    assert.deepEqual(
      closed.tabs.map((item) => item.key),
      ['/dashboard', '/products/list', '/orders/list'],
    );
    assert.equal(closed.activeKey, '/orders/list');
  });

  it('关闭其他保留当前与固定工作台', () => {
    let state = visit('/products/list');
    state = ensureTab(state, '/orders/list', routes);
    state = closeOtherTabs(state, '/orders/list');
    assert.deepEqual(
      state.tabs.map((item) => item.key),
      ['/dashboard', '/orders/list'],
    );
    assert.equal(state.activeKey, '/orders/list');
  });

  it('超过 MAX_TABS 时关掉最早的非固定非当前 Tab', () => {
    let tabs = [createPinnedDashboardTab()];
    for (let index = 1; index <= MAX_TABS + 2; index += 1) {
      tabs.push({
        key: `/orders/${index}`,
        path: `/orders/${index}`,
        title: `订单 ${index}`,
        closable: true,
        tenantScoped: true,
      });
    }
    const limited = enforceMaxTabs(tabs, `/orders/${MAX_TABS + 2}`);
    assert.equal(limited.length, MAX_TABS);
    assert.equal(limited[0]?.key, '/dashboard');
    assert.equal(limited.some((item) => item.key === '/orders/1'), false);
    assert.equal(limited.some((item) => item.key === `/orders/${MAX_TABS + 2}`), true);
  });
});

describe('ERP TabBar 租户、权限、持久化过滤与标题', () => {
  it('租户切换重置为工作台；详情页在切换后不应立刻入 Tab', () => {
    const reset = resetTabsForTenant(9);
    assert.equal(reset.tenantId, 9);
    assert.deepEqual(
      reset.tabs.map((item) => item.key),
      ['/dashboard'],
    );
    assert.equal(shouldSkipTabAfterTenantChange('/orders/123', routes), true);
    assert.equal(shouldSkipTabAfterTenantChange('/orders/12/edit', routes), true);
    assert.equal(shouldSkipTabAfterTenantChange('/after-sales/9', routes), true);
    assert.equal(shouldSkipTabAfterTenantChange('/orders/list', routes), false);
    assert.equal(shouldSkipTabAfterTenantChange('/dashboard', routes), false);
  });

  it('权限变化后清除不可访问 Tab；无效旧路由一并过滤', () => {
    let state = visit('/products/list');
    state = ensureTab(state, '/system/members', routes);
    state = pruneInvalidTabs(state, routes, [PERMISSION_CODE.productRead]);
    assert.equal(state.tabs.some((item) => item.key === '/system/members'), false);
    assert.equal(state.tabs.some((item) => item.key === '/products/list'), true);
    const dirty = {
      ...createInitialTabsState(1),
      tabs: [
        createPinnedDashboardTab(),
        {
          key: '/legacy-removed',
          path: '/legacy-removed',
          title: '已删除',
          closable: true,
          tenantScoped: true,
        },
      ],
      activeKey: '/legacy-removed',
    };
    const cleaned = pruneInvalidTabs(dirty, routes);
    assert.equal(cleaned.tabs.some((item) => item.key === '/legacy-removed'), false);
    assert.equal(cleaned.activeKey, '/dashboard');
  });

  it('拖拽顺序写入 Zustand，工作台始终固定第一且不能排到后面', () => {
    let state = visit('/products/list');
    state = ensureTab(state, '/orders/list', routes);
    state = reorderTabs(state, ['/orders/list', '/dashboard', '/products/list']);
    assert.deepEqual(
      state.tabs.map((item) => item.key),
      ['/dashboard', '/orders/list', '/products/list'],
    );
  });

  it('更新详情 title 不新建第二个 Tab', () => {
    let state = visit('/orders/123');
    state = setTabTitle(state, '/orders/123', '销售订单 SO2026000012');
    state = ensureTab(state, '/orders/123', routes);
    const orderTabs = state.tabs.filter((item) => item.key === '/orders/123');
    assert.equal(orderTabs.length, 1);
    assert.equal(orderTabs[0]?.title, '销售订单 SO2026000012');
  });
});
