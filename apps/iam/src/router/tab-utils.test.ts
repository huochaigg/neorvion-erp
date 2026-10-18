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

describe('IAM TabBar 路径与唯一性', () => {
  it('忽略 query，列表分页不会制造多个 Tab', () => {
    assert.equal(normalizeTabPath('/system/members', '?page=1'), '/system/members');
    assert.equal(normalizeTabPath('/system/members?page=2'), '/system/members');
    assert.equal(normalizeTabPath('/system/members/'), '/system/members');
    let state = visit('/system/members?page=1');
    state = ensureTab(state, '/system/members?page=2', routes);
    assert.equal(state.tabs.filter((item) => item.path === '/system/members').length, 1);
    assert.equal(state.activeKey, '/system/members');
  });

  it('动态详情页按完整 path 区分，不按 route.name', () => {
    let state = visit('/system/members/123');
    state = ensureTab(state, '/system/members/456', routes);
    const keys = state.tabs.map((item) => item.key);
    assert.equal(keys.includes('/system/members/123'), true);
    assert.equal(keys.includes('/system/members/456'), true);
    assert.equal(state.tabs.filter((item) => item.title === '成员详情').length, 2);
  });

  it('重复访问同一路由只激活，不重复创建', () => {
    let state = visit('/system/roles');
    state = ensureTab(state, '/system/roles', routes);
    state = ensureTab(state, '/system/roles', routes);
    assert.equal(state.tabs.filter((item) => item.key === '/system/roles').length, 1);
    assert.equal(state.activeKey, '/system/roles');
  });

  it('未知路由不入 Tab，正式叶子路由才入', () => {
    assert.equal(isTabEligiblePath('/unknown', routes), false);
    assert.equal(isTabEligiblePath('/login', routes), false);
    assert.equal(isTabEligiblePath('/system/members', routes), true);
    const skipped = ensureTab(createInitialTabsState(1), '/unknown', routes);
    assert.deepEqual(
      skipped.tabs.map((item) => item.key),
      ['/dashboard'],
    );
    const opened = ensureTab(skipped, '/system/roles', routes);
    assert.equal(opened.tabs.some((item) => item.key === '/system/roles'), true);
    assert.equal(opened.tabs.find((item) => item.key === '/system/roles')?.title, '角色管理');
  });

  it('工作台与角色页标题来自 routes metadata', () => {
    assert.equal(tabFromPath('/dashboard', routes)?.title, '权限工作台');
    assert.equal(tabFromPath('/system/roles', routes)?.title, '角色管理');
    assert.equal(tabFromPath('/system/roles', routes)?.closable, true);
    assert.equal(tabFromPath('/dashboard', routes)?.closable, false);
  });
});

describe('IAM TabBar 关闭与上限', () => {
  it('Dashboard 固定且不可关闭，关闭全部仍保留工作台', () => {
    let state = visit('/system/roles');
    state = ensureTab(state, '/system/members', routes);
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
    state = ensureTab(state, '/system/roles', routes);
    state = ensureTab(state, '/system/members', routes);
    state = ensureTab(state, '/sessions', routes);
    const idle = closeTab(state, '/system/roles');
    assert.equal(idle.activeKey, '/sessions');
    assert.equal(idle.tabs.some((item) => item.key === '/system/roles'), false);
    const closedActive = closeTab(state, '/sessions');
    assert.equal(closedActive.activeKey, '/system/members');
    let onlyRight = createInitialTabsState(1);
    onlyRight = ensureTab(onlyRight, '/system/members', routes);
    onlyRight = closeTab(onlyRight, '/system/members');
    assert.equal(onlyRight.activeKey, '/dashboard');
  });

  it('关闭右侧只去掉目标右侧的可关闭 Tab，工作台保留', () => {
    let state = createInitialTabsState(1);
    state = ensureTab(state, '/system/roles', routes);
    state = ensureTab(state, '/system/members', routes);
    state = ensureTab(state, '/sessions', routes);
    const closed = closeTabsToTheRight(state, '/system/members');
    assert.deepEqual(
      closed.tabs.map((item) => item.key),
      ['/dashboard', '/system/roles', '/system/members'],
    );
    assert.equal(closed.activeKey, '/system/members');
  });

  it('关闭其他保留当前与固定工作台', () => {
    let state = visit('/system/roles');
    state = ensureTab(state, '/system/members', routes);
    state = closeOtherTabs(state, '/system/members');
    assert.deepEqual(
      state.tabs.map((item) => item.key),
      ['/dashboard', '/system/members'],
    );
    assert.equal(state.activeKey, '/system/members');
  });

  it('超过 MAX_TABS 时关掉最早的非固定非当前 Tab', () => {
    let tabs = [createPinnedDashboardTab()];
    for (let index = 1; index <= MAX_TABS + 2; index += 1) {
      tabs.push({
        key: `/system/members/${index}`,
        path: `/system/members/${index}`,
        title: `成员 ${index}`,
        closable: true,
        tenantScoped: true,
      });
    }
    const limited = enforceMaxTabs(tabs, `/system/members/${MAX_TABS + 2}`);
    assert.equal(limited.length, MAX_TABS);
    assert.equal(limited[0]?.key, '/dashboard');
    assert.equal(limited.some((item) => item.key === '/system/members/1'), false);
    assert.equal(limited.some((item) => item.key === `/system/members/${MAX_TABS + 2}`), true);
  });
});

describe('IAM TabBar 租户、权限、持久化过滤与标题', () => {
  it('租户切换重置为工作台；详情页在切换后不应立刻入 Tab', () => {
    const reset = resetTabsForTenant(9);
    assert.equal(reset.tenantId, 9);
    assert.deepEqual(
      reset.tabs.map((item) => item.key),
      ['/dashboard'],
    );
    assert.equal(shouldSkipTabAfterTenantChange('/system/members/123', routes), true);
    assert.equal(shouldSkipTabAfterTenantChange('/system/members', routes), false);
    assert.equal(shouldSkipTabAfterTenantChange('/dashboard', routes), false);
  });

  it('权限变化后清除不可访问 Tab；无效旧路由一并过滤', () => {
    let state = visit('/system/roles');
    state = ensureTab(state, '/system/members', routes);
    state = pruneInvalidTabs(state, routes, [PERMISSION_CODE.tenantRoleRead]);
    assert.equal(state.tabs.some((item) => item.key === '/system/members'), false);
    assert.equal(state.tabs.some((item) => item.key === '/system/roles'), true);
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
    let state = visit('/system/roles');
    state = ensureTab(state, '/system/members', routes);
    state = reorderTabs(state, ['/system/members', '/dashboard', '/system/roles']);
    assert.deepEqual(
      state.tabs.map((item) => item.key),
      ['/dashboard', '/system/members', '/system/roles'],
    );
  });

  it('更新详情 title 不新建第二个 Tab', () => {
    let state = visit('/system/members/123');
    state = setTabTitle(state, '/system/members/123', '成员 张三');
    state = ensureTab(state, '/system/members/123', routes);
    const memberTabs = state.tabs.filter((item) => item.key === '/system/members/123');
    assert.equal(memberTabs.length, 1);
    assert.equal(memberTabs[0]?.title, '成员 张三');
  });
});
