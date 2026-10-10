import assert from 'node:assert/strict';
import { PERMISSION_CODE } from '@neorvion/shared';
import { describe, it } from 'vitest';
import {
  filterMenuRoutes,
  pageAllowsAccess,
  resolvePageAccessState,
} from './access';
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
  it('有权限显示菜单，无权限隐藏，一级二级三级递归正常', () => {
    const viewer = [
      PERMISSION_CODE.productRead,
      PERMISSION_CODE.tenantMemberRead,
      PERMISSION_CODE.tenantRoleRead,
      PERMISSION_CODE.tenantPermissionRead,
    ];
    const paths = menuPaths(filterMenuRoutes(routes, viewer));
    assert.equal(paths.includes('/dashboard'), true);
    assert.equal(paths.includes('/products'), true);
    assert.equal(paths.includes('/products/list'), true);
    assert.equal(paths.includes('/product-categories'), true);
    assert.equal(paths.includes('/brands'), true);
    assert.equal(paths.includes('/products/archive'), false);
    assert.equal(paths.includes('/system'), true);
    assert.equal(paths.includes('/system/members'), true);
    assert.equal(paths.includes('/system/roles'), true);
    assert.equal(paths.includes('/system/permissions'), true);
    assert.equal(paths.includes('/inventory'), false);
    assert.equal(paths.includes('/warehouses'), false);
    assert.equal(paths.includes('/purchases'), false);
    assert.equal(paths.includes('/suppliers'), false);
    assert.equal(paths.includes('/products/create'), false);
  });

  it('父级没有任何可见子菜单时隐藏空分组，部分子菜单无权限时父级仍在', () => {
    const onlyMembers = [PERMISSION_CODE.tenantMemberRead];
    const paths = menuPaths(filterMenuRoutes(routes, onlyMembers));
    assert.equal(paths.includes('/system'), true);
    assert.equal(paths.includes('/system/members'), true);
    assert.equal(paths.includes('/system/roles'), false);
    const noSystem = [PERMISSION_CODE.productRead];
    const productOnly = menuPaths(filterMenuRoutes(routes, noSystem));
    assert.equal(productOnly.includes('/system'), false);
    assert.equal(productOnly.includes('/products'), true);
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
    const createMatch = matchRoute(routes, '/products/create');
    assert.equal(pageAllowsAccess(createMatch, [PERMISSION_CODE.productRead]), false);
    assert.equal(pageAllowsAccess(createMatch, [PERMISSION_CODE.productCreate]), true);
    const categoryMatch = matchRoute(routes, '/product-categories');
    assert.equal(pageAllowsAccess(categoryMatch, []), false);
    assert.equal(pageAllowsAccess(categoryMatch, [PERMISSION_CODE.productRead]), true);
    const brandMatch = matchRoute(routes, '/brands');
    assert.equal(pageAllowsAccess(brandMatch, [PERMISSION_CODE.productRead]), true);
    const warehouseMatch = matchRoute(routes, '/warehouses');
    assert.equal(pageAllowsAccess(warehouseMatch, [PERMISSION_CODE.productRead]), false);
    assert.equal(pageAllowsAccess(warehouseMatch, [PERMISSION_CODE.warehouseRead]), true);
    const inventoryList = matchRoute(routes, '/inventory/list');
    assert.equal(pageAllowsAccess(inventoryList, [PERMISSION_CODE.productRead]), false);
    assert.equal(pageAllowsAccess(inventoryList, [PERMISSION_CODE.inventoryRead]), true);
    const inventoryTx = matchRoute(routes, '/inventory/transactions');
    assert.equal(pageAllowsAccess(inventoryTx, [PERMISSION_CODE.inventoryRead]), false);
    assert.equal(pageAllowsAccess(inventoryTx, [PERMISSION_CODE.inventoryTransactionRead]), true);
    const inventoryDetail = matchRoute(routes, '/inventory/88');
    assert.equal(pageAllowsAccess(inventoryDetail, []), false);
    assert.equal(pageAllowsAccess(inventoryDetail, [PERMISSION_CODE.inventoryRead]), true);
    const purchaseList = matchRoute(routes, '/purchases/list');
    assert.equal(pageAllowsAccess(purchaseList, [PERMISSION_CODE.productRead]), false);
    assert.equal(pageAllowsAccess(purchaseList, [PERMISSION_CODE.purchaseRead]), true);
    const purchaseCreate = matchRoute(routes, '/purchases/create');
    assert.equal(pageAllowsAccess(purchaseCreate, [PERMISSION_CODE.purchaseRead]), false);
    assert.equal(pageAllowsAccess(purchaseCreate, [PERMISSION_CODE.purchaseCreate]), true);
    const purchaseEdit = matchRoute(routes, '/purchases/9/edit');
    assert.equal(pageAllowsAccess(purchaseEdit, [PERMISSION_CODE.purchaseRead]), false);
    assert.equal(pageAllowsAccess(purchaseEdit, [PERMISSION_CODE.purchaseUpdate]), true);
    const purchaseDetail = matchRoute(routes, '/purchases/9');
    assert.equal(pageAllowsAccess(purchaseDetail, []), false);
    assert.equal(pageAllowsAccess(purchaseDetail, [PERMISSION_CODE.purchaseRead]), true);
    const receiptList = matchRoute(routes, '/purchase-receipts');
    assert.equal(pageAllowsAccess(receiptList, [PERMISSION_CODE.purchaseRead]), false);
    assert.equal(pageAllowsAccess(receiptList, [PERMISSION_CODE.purchaseReceiptRead]), true);
    const receiptCreate = matchRoute(routes, '/purchase-receipts/create');
    assert.equal(pageAllowsAccess(receiptCreate, [PERMISSION_CODE.purchaseReceiptRead]), false);
    assert.equal(pageAllowsAccess(receiptCreate, [PERMISSION_CODE.purchaseReceiptCreate]), true);
    const receiptDetail = matchRoute(routes, '/purchase-receipts/9');
    assert.equal(pageAllowsAccess(receiptDetail, []), false);
    assert.equal(pageAllowsAccess(receiptDetail, [PERMISSION_CODE.purchaseReceiptRead]), true);
    const outboundList = matchRoute(routes, '/outbound-orders');
    assert.equal(pageAllowsAccess(outboundList, [PERMISSION_CODE.inventoryRead]), false);
    assert.equal(pageAllowsAccess(outboundList, [PERMISSION_CODE.outboundRead]), true);
    const outboundDetail = matchRoute(routes, '/outbound-orders/3');
    assert.equal(pageAllowsAccess(outboundDetail, []), false);
    assert.equal(pageAllowsAccess(outboundDetail, [PERMISSION_CODE.outboundRead]), true);
    const suppliers = matchRoute(routes, '/suppliers');
    assert.equal(pageAllowsAccess(suppliers, [PERMISSION_CODE.purchaseRead]), false);
    assert.equal(pageAllowsAccess(suppliers, [PERMISSION_CODE.supplierRead]), true);
    const shipmentList = matchRoute(routes, '/shipments');
    assert.equal(pageAllowsAccess(shipmentList, [PERMISSION_CODE.outboundRead]), false);
    assert.equal(pageAllowsAccess(shipmentList, [PERMISSION_CODE.shipmentRead]), true);
    const shipmentCreate = matchRoute(routes, '/shipments/create');
    assert.equal(pageAllowsAccess(shipmentCreate, [PERMISSION_CODE.shipmentRead]), false);
    assert.equal(pageAllowsAccess(shipmentCreate, [PERMISSION_CODE.shipmentCreate]), true);
    const shipmentDetail = matchRoute(routes, '/shipments/9');
    assert.equal(pageAllowsAccess(shipmentDetail, []), false);
    assert.equal(pageAllowsAccess(shipmentDetail, [PERMISSION_CODE.shipmentRead]), true);
    const carriers = matchRoute(routes, '/carriers');
    assert.equal(pageAllowsAccess(carriers, [PERMISSION_CODE.shipmentRead]), false);
    assert.equal(pageAllowsAccess(carriers, [PERMISSION_CODE.carrierRead]), true);
    const stocktakeList = matchRoute(routes, '/stocktakes');
    assert.equal(pageAllowsAccess(stocktakeList, [PERMISSION_CODE.inventoryRead]), false);
    assert.equal(pageAllowsAccess(stocktakeList, [PERMISSION_CODE.stocktakeRead]), true);
    const stocktakeDetail = matchRoute(routes, '/stocktakes/9');
    assert.equal(pageAllowsAccess(stocktakeDetail, []), false);
    assert.equal(pageAllowsAccess(stocktakeDetail, [PERMISSION_CODE.stocktakeRead]), true);
    const stocktakeCreate = matchRoute(routes, '/stocktakes/create');
    assert.equal(pageAllowsAccess(stocktakeCreate, [PERMISSION_CODE.stocktakeRead]), false);
    assert.equal(pageAllowsAccess(stocktakeCreate, [PERMISSION_CODE.stocktakeCreate]), true);
    const transferList = matchRoute(routes, '/stock-transfers');
    assert.equal(pageAllowsAccess(transferList, [PERMISSION_CODE.inventoryRead]), false);
    assert.equal(pageAllowsAccess(transferList, [PERMISSION_CODE.stockTransferRead]), true);
    const transferCreate = matchRoute(routes, '/stock-transfers/create');
    assert.equal(pageAllowsAccess(transferCreate, [PERMISSION_CODE.stockTransferRead]), false);
    assert.equal(pageAllowsAccess(transferCreate, [PERMISSION_CODE.stockTransferCreate]), true);
    const transferEdit = matchRoute(routes, '/stock-transfers/4/edit');
    assert.equal(pageAllowsAccess(transferEdit, [PERMISSION_CODE.stockTransferRead]), false);
    assert.equal(pageAllowsAccess(transferEdit, [PERMISSION_CODE.stockTransferUpdate]), true);
    const transferDetail = matchRoute(routes, '/stock-transfers/4');
    assert.equal(pageAllowsAccess(transferDetail, []), false);
    assert.equal(pageAllowsAccess(transferDetail, [PERMISSION_CODE.stockTransferRead]), true);
  });

  it('租户 A 与 B 权限独立：仓库身份看不到系统管理', () => {
    const warehouse = [
      PERMISSION_CODE.productRead,
      PERMISSION_CODE.orderRead,
      PERMISSION_CODE.inventoryRead,
      PERMISSION_CODE.warehouseRead,
    ];
    const admin = [
      PERMISSION_CODE.tenantMemberRead,
      PERMISSION_CODE.tenantRoleRead,
      PERMISSION_CODE.tenantPermissionRead,
      PERMISSION_CODE.productRead,
    ];
    const warehouseMenu = menuPaths(filterMenuRoutes(routes, warehouse));
    const adminMenu = menuPaths(filterMenuRoutes(routes, admin));
    assert.equal(warehouseMenu.includes('/system'), false);
    assert.equal(warehouseMenu.includes('/inventory'), true);
    assert.equal(warehouseMenu.includes('/warehouses'), true);
    assert.equal(adminMenu.includes('/system'), true);
    assert.notDeepEqual(warehouseMenu, adminMenu);
  });

  it('角色权限变更后菜单随编码重新计算', () => {
    const before = [PERMISSION_CODE.tenantMemberRead, PERMISSION_CODE.tenantRoleRead];
    const after = [PERMISSION_CODE.tenantMemberRead];
    assert.equal(menuPaths(filterMenuRoutes(routes, before)).includes('/system/roles'), true);
    assert.equal(menuPaths(filterMenuRoutes(routes, after)).includes('/system/roles'), false);
  });

  it('未声明权限的工作台对有效成员开放', () => {
    const dashboard = matchRoute(routes, '/dashboard');
    assert.equal(pageAllowsAccess(dashboard, []), true);
  });
});
