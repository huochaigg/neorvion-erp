import assert from 'node:assert/strict';
import {
  canAccess,
  canCancelSalesOrder,
  canConfirmSalesOrder,
  canCreateOutbound,
  canEditSalesOrder,
  canSubmitSalesOrder,
  customersQueryKey,
  formatSalesInventoryShortage,
  mergeSalesSkuLine,
  PERMISSION_CODE,
  SALES_ORDER_STATUS,
  salesOrderQueryKey,
  salesOrdersQueryKey,
  salesOrderStatusLabel,
  outboundOrderQueryKey,
  outboundOrdersQueryKey,
  skuInventoryQueryKey,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('销售订单与客户 UI 规则', () => {
  it('客户按钮与后端权限编码一致', () => {
    const viewer = [PERMISSION_CODE.customerRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.customerCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.customerUpdate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.customerDisable]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.customerDelete]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.customerRead]), true);
  });

  it('订单操作按状态显示，待出库只能取消', () => {
    assert.equal(canEditSalesOrder(SALES_ORDER_STATUS.draft), true);
    assert.equal(canEditSalesOrder(SALES_ORDER_STATUS.pendingConfirmation), false);
    assert.equal(canSubmitSalesOrder(SALES_ORDER_STATUS.draft), true);
    assert.equal(canConfirmSalesOrder(SALES_ORDER_STATUS.pendingConfirmation), true);
    assert.equal(canConfirmSalesOrder(SALES_ORDER_STATUS.waitingOutbound), false);
    assert.equal(canCancelSalesOrder(SALES_ORDER_STATUS.waitingOutbound), true);
    assert.equal(canCancelSalesOrder(SALES_ORDER_STATUS.partiallyOutbound), false);
    assert.equal(canCancelSalesOrder(SALES_ORDER_STATUS.partiallyShipped), false);
    assert.equal(canCancelSalesOrder(SALES_ORDER_STATUS.shipped), false);
    assert.equal(canCreateOutbound(SALES_ORDER_STATUS.waitingOutbound), true);
    assert.equal(canCreateOutbound(SALES_ORDER_STATUS.partiallyOutbound), true);
    assert.equal(canCreateOutbound(SALES_ORDER_STATUS.partiallyShipped), true);
    assert.equal(canCreateOutbound(SALES_ORDER_STATUS.outbounded), false);
    assert.equal(canCreateOutbound(SALES_ORDER_STATUS.shipped), false);
    assert.equal(salesOrderStatusLabel(SALES_ORDER_STATUS.waitingOutbound), '待出库');
    assert.equal(salesOrderStatusLabel(SALES_ORDER_STATUS.partiallyOutbound), '部分出库');
    assert.equal(salesOrderStatusLabel(SALES_ORDER_STATUS.outbounded), '已出库');
    assert.equal(salesOrderStatusLabel(SALES_ORDER_STATUS.partiallyShipped), '部分发货');
    assert.equal(salesOrderStatusLabel(SALES_ORDER_STATUS.shipped), '已发货');
    assert.equal(salesOrderStatusLabel(SALES_ORDER_STATUS.completed), '已完成');
    assert.equal(salesOrderStatusLabel(SALES_ORDER_STATUS.pendingConfirmation), '待确认');
  });

  it('运营可以提交和取消，不能确认', () => {
    const operator = [
      PERMISSION_CODE.orderRead,
      PERMISSION_CODE.orderCreate,
      PERMISSION_CODE.orderUpdate,
      PERMISSION_CODE.orderSubmit,
      PERMISSION_CODE.orderCancel,
    ];
    assert.equal(canAccess(operator, [PERMISSION_CODE.orderSubmit]), true);
    assert.equal(canAccess(operator, [PERMISSION_CODE.orderAudit]), false);
    assert.equal(canAccess(operator, [PERMISSION_CODE.orderCancel]), true);
    assert.equal(canAccess(operator, [PERMISSION_CODE.outboundRead]), false);
    assert.equal(canAccess([PERMISSION_CODE.outboundRead], [PERMISSION_CODE.outboundConfirm]), false);
    assert.equal(
      canAccess(
        [PERMISSION_CODE.outboundRead, PERMISSION_CODE.outboundPick, PERMISSION_CODE.outboundConfirm],
        [PERMISSION_CODE.outboundConfirm],
      ),
      true,
    );
  });

  it('Query Key 含 tenantId，确认后库存查询键和订单键互相独立', () => {
    assert.notDeepEqual(customersQueryKey(1), customersQueryKey(2));
    assert.notDeepEqual(salesOrdersQueryKey(1), salesOrdersQueryKey(2));
    assert.notDeepEqual(
      salesOrdersQueryKey(1, { status: 'DRAFT', page: 1, pageSize: 20 }),
      salesOrdersQueryKey(1, { status: 'WAITING_OUTBOUND', page: 1, pageSize: 20 }),
    );
    assert.notDeepEqual(salesOrderQueryKey(1, 8), salesOrderQueryKey(2, 8));
    assert.notDeepEqual(outboundOrdersQueryKey(1), outboundOrdersQueryKey(2));
    assert.notDeepEqual(outboundOrderQueryKey(1, 6), outboundOrderQueryKey(2, 6));
    assert.notDeepEqual(skuInventoryQueryKey(1, 3, [2, 1]), skuInventoryQueryKey(2, 3, [1, 2]));
    assert.deepEqual(skuInventoryQueryKey(1, 3, [2, 1])[4], [1, 2]);
  });

  it('重复 SKU 合并数量，库存不足文案带出 SKU 和数量', () => {
    const first = mergeSalesSkuLine([], {
      sku_id: 1,
      sku_code: 'SKU-A',
      sku_name: 'A',
      product_name: '手机',
      spec_values: {},
      quantity: 2,
      unit_price: 3,
    });
    const second = mergeSalesSkuLine(first.items, {
      sku_id: 1,
      sku_code: 'SKU-A',
      sku_name: 'A',
      product_name: '手机',
      spec_values: {},
      quantity: 4,
      unit_price: null,
    });
    assert.equal(second.merged, true);
    assert.equal(second.items[0].quantity, 6);
    const text = formatSalesInventoryShortage(
      {
        error: 'INSUFFICIENT_AVAILABLE_INVENTORY',
        items: [{ sku_code: 'SKU000001', available_quantity: 3, requested_quantity: 5 }],
      },
      '操作失败',
    );
    assert.equal(text, 'SKU000001 可用库存 3，订单需要 5。');
  });
});
