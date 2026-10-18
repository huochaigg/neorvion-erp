import assert from 'node:assert/strict';
import { PERMISSION_CODE } from '@neorvion/shared';
import { describe, it } from 'vitest';
import { filterMenuRoutes, pageAllowsAccess, resolvePageAccessState } from './access';
import { matchRoute } from './match';
import { routes } from './routes';

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

describe('动态权限菜单与页面守卫', () => {
  it('有权限显示菜单，无权限隐藏', () => {
    const viewer = [
      PERMISSION_CODE.tenantMemberRead,
      PERMISSION_CODE.tenantRoleRead,
      PERMISSION_CODE.tenantPermissionRead,
    ];
    const paths = menuPaths(filterMenuRoutes(routes, viewer));
    assert.equal(paths.includes('/dashboard'), true);
    assert.equal(paths.includes('/system/members'), true);
    assert.equal(paths.includes('/system/roles'), true);
    assert.equal(paths.includes('/system/permissions'), true);
    assert.equal(paths.includes('/users'), false);
    assert.equal(paths.includes('/applications'), false);
    assert.equal(paths.includes('/sessions'), true);
  });

  it('仅成员权限时不显示角色与应用', () => {
    const onlyMembers = [PERMISSION_CODE.tenantMemberRead];
    const paths = menuPaths(filterMenuRoutes(routes, onlyMembers));
    assert.equal(paths.includes('/system/members'), true);
    assert.equal(paths.includes('/system/roles'), false);
    assert.equal(paths.includes('/applications'), false);
  });

  it('无权限直接访问 URL 判定为 403，加载中不放行受保护页', () => {
    const membersMatch = matchRoute(routes, '/system/members');
    assert.equal(pageAllowsAccess(membersMatch, []), false);
    assert.equal(pageAllowsAccess(membersMatch, [PERMISSION_CODE.tenantMemberRead]), true);
    assert.equal(
      resolvePageAccessState({
        tenantId: 8,
        isLoading: true,
        match: membersMatch,
        permissions: [PERMISSION_CODE.tenantMemberRead],
      }),
      'loading',
    );
    assert.equal(
      resolvePageAccessState({
        tenantId: 8,
        isLoading: false,
        match: membersMatch,
        permissions: [],
      }),
      'forbidden',
    );
    assert.equal(
      resolvePageAccessState({
        tenantId: 8,
        isLoading: false,
        match: membersMatch,
        permissions: [PERMISSION_CODE.tenantMemberRead],
      }),
      'allow',
    );
  });

  it('隐藏菜单的详情页仍要权限，不能因 showInMenu:false 放行', () => {
    const detailMatch = matchRoute(routes, '/system/members/12');
    assert.equal(pageAllowsAccess(detailMatch, []), false);
    assert.equal(pageAllowsAccess(detailMatch, [PERMISSION_CODE.tenantMemberRead]), true);
    const appsMatch = matchRoute(routes, '/applications');
    assert.equal(pageAllowsAccess(appsMatch, [PERMISSION_CODE.tenantMemberRead]), false);
    assert.equal(pageAllowsAccess(appsMatch, [PERMISSION_CODE.iamAppsRead]), true);
  });

  it('平台用户管理与租户成员菜单权限独立', () => {
    const tenantAdmin = [
      PERMISSION_CODE.tenantMemberRead,
      PERMISSION_CODE.tenantRoleRead,
      PERMISSION_CODE.tenantPermissionRead,
    ];
    const platform = [PERMISSION_CODE.iamUsersRead, PERMISSION_CODE.iamAppsRead];
    const tenantMenu = menuPaths(filterMenuRoutes(routes, tenantAdmin));
    const platformMenu = menuPaths(filterMenuRoutes(routes, platform));
    assert.equal(tenantMenu.includes('/users'), false);
    assert.equal(tenantMenu.includes('/system/members'), true);
    assert.equal(platformMenu.includes('/users'), true);
    assert.equal(platformMenu.includes('/system/members'), false);
    assert.notDeepEqual(tenantMenu, platformMenu);
  });

  it('角色权限变更后菜单随编码重新计算', () => {
    const before = [PERMISSION_CODE.tenantMemberRead, PERMISSION_CODE.tenantRoleRead];
    const after = [PERMISSION_CODE.tenantMemberRead];
    assert.equal(menuPaths(filterMenuRoutes(routes, before)).includes('/system/roles'), true);
    assert.equal(menuPaths(filterMenuRoutes(routes, after)).includes('/system/roles'), false);
  });

  it('未声明权限的工作台与会话页对有效成员开放', () => {
    const dashboard = matchRoute(routes, '/dashboard');
    assert.equal(pageAllowsAccess(dashboard, []), true);
    const sessions = matchRoute(routes, '/sessions');
    assert.equal(pageAllowsAccess(sessions, []), true);
  });
});
