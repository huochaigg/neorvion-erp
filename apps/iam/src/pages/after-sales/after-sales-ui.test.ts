import assert from 'node:assert/strict';
import {
  AFTER_SALE_STATUS,
  AFTER_SALE_TYPE,
  afterSaleQueryKey,
  afterSalesQueryKey,
  afterSaleStatusLabel,
  afterSaleTypeLabel,
  canAccess,
  canApplyAfterSale,
  canApproveAfterSale,
  canConfirmRefundRecord,
  canConfirmReturnInbound,
  canCreateRefund,
  canReceiveReturn,
  defaultInboundQuantity,
  PERMISSION_CODE,
  refundsQueryKey,
  RETURN_CONDITION,
  RETURN_ORDER_STATUS,
  returnOrdersQueryKey,
  SALES_ORDER_STATUS,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('售后页 UI 规则', () => {
  it('按钮与后端权限编码一致：无对应 code 不显示操作', () => {
    const viewer = [PERMISSION_CODE.afterSaleRead, PERMISSION_CODE.returnOrderRead, PERMISSION_CODE.refundRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.afterSaleCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.afterSaleApprove]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.returnOrderReceive]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.returnOrderInbound]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.refundConfirm]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.afterSaleRead]), true);
    const warehouse = [
      PERMISSION_CODE.afterSaleRead,
      PERMISSION_CODE.returnOrderRead,
      PERMISSION_CODE.returnOrderReceive,
      PERMISSION_CODE.returnOrderInbound,
    ];
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.returnOrderInbound]), true);
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.refundConfirm]), false);
  });

  it('Query Key 含 tenantId 和筛选条件', () => {
    assert.notDeepEqual(afterSalesQueryKey(1), afterSalesQueryKey(2));
    assert.notDeepEqual(
      afterSalesQueryKey(1, { status: 'PENDING_APPROVAL' }),
      afterSalesQueryKey(1, { status: 'COMPLETED' }),
    );
    assert.notDeepEqual(afterSaleQueryKey(1, 9), afterSaleQueryKey(2, 9));
    assert.notDeepEqual(returnOrdersQueryKey(1), returnOrdersQueryKey(2));
    assert.notDeepEqual(refundsQueryKey(1), refundsQueryKey(2));
  });

  it('状态机与可退规则：未出库不能申请，审核前后占用数量', () => {
    assert.equal(canApplyAfterSale(SALES_ORDER_STATUS.waitingOutbound), false);
    assert.equal(canApplyAfterSale(SALES_ORDER_STATUS.outbounded), true);
    assert.equal(canApproveAfterSale(AFTER_SALE_STATUS.pendingApproval), true);
    assert.equal(canApproveAfterSale(AFTER_SALE_STATUS.waitingReturn), false);
    assert.equal(canCreateRefund(AFTER_SALE_STATUS.waitingRefund, AFTER_SALE_TYPE.refundOnly), true);
    assert.equal(canCreateRefund(AFTER_SALE_STATUS.waitingReturn, AFTER_SALE_TYPE.returnAndRefund), false);
    assert.equal(canCreateRefund(AFTER_SALE_STATUS.waitingRefund, AFTER_SALE_TYPE.returnOnly), false);
    assert.equal(canReceiveReturn(RETURN_ORDER_STATUS.waitingReturn), true);
    assert.equal(canReceiveReturn(RETURN_ORDER_STATUS.received), false);
    assert.equal(canConfirmReturnInbound(RETURN_ORDER_STATUS.received, 3), true);
    assert.equal(canConfirmReturnInbound(RETURN_ORDER_STATUS.inbounded, 3), false);
    assert.equal(defaultInboundQuantity(RETURN_CONDITION.good, 3), 3);
    assert.equal(defaultInboundQuantity(RETURN_CONDITION.damaged, 3), 0);
    assert.equal(defaultInboundQuantity(RETURN_CONDITION.unsellable, 2), 0);
    assert.equal(canConfirmRefundRecord('PENDING'), true);
    assert.equal(canConfirmRefundRecord('SUCCESS'), false);
    assert.equal(afterSaleTypeLabel(AFTER_SALE_TYPE.refundOnly), '仅退款');
    assert.equal(afterSaleStatusLabel(AFTER_SALE_STATUS.waitingRefund), '待退款');
  });
});
