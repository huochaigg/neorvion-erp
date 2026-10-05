import assert from 'node:assert/strict';
import {
  canAccess,
  canApprovePurchaseOrder,
  canCancelPurchaseOrder,
  canEditPurchaseOrder,
  canRejectPurchaseOrder,
  canSubmitPurchaseOrder,
  formatPurchaseAmount,
  mergePurchaseSkuLine,
  PERMISSION_CODE,
  PURCHASE_ORDER_STATUS,
  purchaseOrderQueryKey,
  purchaseOrdersQueryKey,
  purchaseOrderStatusLabel,
  supplierLocation,
  supplierQueryKey,
  suppliersQueryKey,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('采购与供应商 UI 规则', () => {
  it('供应商按钮与后端权限编码一致', () => {
    const viewer = [PERMISSION_CODE.supplierRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.supplierCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.supplierUpdate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.supplierDisable]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.supplierDelete]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.supplierRead]), true);
    const operator = [PERMISSION_CODE.supplierRead, PERMISSION_CODE.purchaseRead];
    assert.equal(canAccess(operator, [PERMISSION_CODE.supplierCreate]), false);
    assert.equal(canAccess(operator, [PERMISSION_CODE.purchaseCreate]), false);
  });

  it('采购操作按状态显示，待收货不能编辑或取消', () => {
    assert.equal(canEditPurchaseOrder(PURCHASE_ORDER_STATUS.draft), true);
    assert.equal(canEditPurchaseOrder(PURCHASE_ORDER_STATUS.rejected), true);
    assert.equal(canEditPurchaseOrder(PURCHASE_ORDER_STATUS.pendingApproval), false);
    assert.equal(canEditPurchaseOrder(PURCHASE_ORDER_STATUS.waitingReceipt), false);
    assert.equal(canSubmitPurchaseOrder(PURCHASE_ORDER_STATUS.draft), true);
    assert.equal(canSubmitPurchaseOrder(PURCHASE_ORDER_STATUS.rejected), true);
    assert.equal(canApprovePurchaseOrder(PURCHASE_ORDER_STATUS.pendingApproval), true);
    assert.equal(canRejectPurchaseOrder(PURCHASE_ORDER_STATUS.pendingApproval), true);
    assert.equal(canCancelPurchaseOrder(PURCHASE_ORDER_STATUS.draft), true);
    assert.equal(canCancelPurchaseOrder(PURCHASE_ORDER_STATUS.waitingReceipt), false);
    assert.equal(purchaseOrderStatusLabel(PURCHASE_ORDER_STATUS.waitingReceipt), '待收货');
  });

  it('运营有提交没有审核，审核按钮应对齐 purchase:audit', () => {
    const operator = [
      PERMISSION_CODE.purchaseRead,
      PERMISSION_CODE.purchaseCreate,
      PERMISSION_CODE.purchaseUpdate,
      PERMISSION_CODE.purchaseSubmit,
      PERMISSION_CODE.purchaseCancel,
    ];
    assert.equal(canAccess(operator, [PERMISSION_CODE.purchaseSubmit]), true);
    assert.equal(canAccess(operator, [PERMISSION_CODE.purchaseAudit]), false);
    assert.equal(canAccess(operator, [PERMISSION_CODE.purchaseCancel]), true);
  });

  it('Query Key 含 tenantId，切租户不会复用列表和详情', () => {
    assert.notDeepEqual(suppliersQueryKey(1), suppliersQueryKey(2));
    assert.notDeepEqual(
      suppliersQueryKey(1, { q: '深圳', page: 1, pageSize: 20 }),
      suppliersQueryKey(1, { q: '广州', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(supplierQueryKey(1, 9), supplierQueryKey(2, 9));
    assert.notDeepEqual(purchaseOrdersQueryKey(1), purchaseOrdersQueryKey(2));
    assert.notDeepEqual(
      purchaseOrdersQueryKey(1, { status: 'DRAFT', page: 1, pageSize: 20 }),
      purchaseOrdersQueryKey(1, { status: 'WAITING_RECEIPT', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(purchaseOrderQueryKey(1, 8), purchaseOrderQueryKey(2, 8));
  });

  it('同一 SKU 再次添加时合并数量，金额缺省显示为 -', () => {
    const first = mergePurchaseSkuLine([], {
      sku_id: 1,
      sku_code: 'SKU-A',
      sku_name: 'A',
      product_name: '手机',
      spec_values: {},
      quantity: 10,
      unit_price: 2,
    });
    assert.equal(first.merged, false);
    const second = mergePurchaseSkuLine(first.items, {
      sku_id: 1,
      sku_code: 'SKU-A',
      sku_name: 'A',
      product_name: '手机',
      spec_values: {},
      quantity: 5,
      unit_price: null,
    });
    assert.equal(second.merged, true);
    assert.equal(second.items.length, 1);
    assert.equal(second.items[0].quantity, 15);
    assert.equal(formatPurchaseAmount(null), '-');
    assert.equal(supplierLocation({ country_code: 'CN', city: '深圳' }), 'CN / 深圳');
  });
});
