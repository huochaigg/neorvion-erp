import assert from 'node:assert/strict';
import {
  canAccess,
  canApprovePurchaseReturn,
  canCancelPurchaseReturn,
  canConfirmPurchaseReturnOutbound,
  canConfirmSupplierRefund,
  canCreatePurchaseReturn,
  canCreatePurchaseReturnOutbound,
  canCreateSupplierRefund,
  canSubmitPurchaseReturn,
  defaultOutboundQuantity,
  PERMISSION_CODE,
  PURCHASE_ORDER_STATUS,
  PURCHASE_RETURN_SETTLEMENT,
  PURCHASE_RETURN_STATUS,
  purchaseReturnQueryKey,
  purchaseReturnsQueryKey,
  purchaseReturnStatusLabel,
  supplierRefundsQueryKey,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('采购退货页 UI 规则', () => {
  it('按钮与后端权限编码一致：无对应 code 不显示操作', () => {
    const viewer = [PERMISSION_CODE.purchaseReturnRead, PERMISSION_CODE.supplierRefundRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.purchaseReturnCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.purchaseReturnApprove]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.purchaseReturnOutbound]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.supplierRefundConfirm]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.purchaseReturnRead]), true);
    const warehouse = [PERMISSION_CODE.purchaseReturnRead, PERMISSION_CODE.purchaseReturnOutbound];
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.purchaseReturnOutbound]), true);
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.supplierRefundConfirm]), false);
  });

  it('Query Key 含 tenantId 和筛选条件', () => {
    assert.notDeepEqual(purchaseReturnsQueryKey(1), purchaseReturnsQueryKey(2));
    assert.notDeepEqual(
      purchaseReturnsQueryKey(1, { status: 'PENDING_APPROVAL' }),
      purchaseReturnsQueryKey(1, { status: 'COMPLETED' }),
    );
    assert.notDeepEqual(purchaseReturnQueryKey(1, 9), purchaseReturnQueryKey(2, 9));
    assert.notDeepEqual(supplierRefundsQueryKey(1), supplierRefundsQueryKey(2));
  });

  it('状态机与可退规则：未收货不能申请，出库只看 available', () => {
    assert.equal(canCreatePurchaseReturn(PURCHASE_ORDER_STATUS.waitingReceipt), false);
    assert.equal(canCreatePurchaseReturn(PURCHASE_ORDER_STATUS.received), true);
    assert.equal(canCreatePurchaseReturn(PURCHASE_ORDER_STATUS.partiallyReceived), true);
    assert.equal(canSubmitPurchaseReturn(PURCHASE_RETURN_STATUS.draft), true);
    assert.equal(canApprovePurchaseReturn(PURCHASE_RETURN_STATUS.pendingApproval), true);
    assert.equal(canApprovePurchaseReturn(PURCHASE_RETURN_STATUS.waitingOutbound), false);
    assert.equal(canCancelPurchaseReturn(PURCHASE_RETURN_STATUS.draft), true);
    assert.equal(canCancelPurchaseReturn(PURCHASE_RETURN_STATUS.waitingOutbound), false);
    assert.equal(canCreatePurchaseReturnOutbound(PURCHASE_RETURN_STATUS.waitingOutbound), true);
    assert.equal(canCreatePurchaseReturnOutbound(PURCHASE_RETURN_STATUS.partiallyReturned), true);
    assert.equal(canConfirmPurchaseReturnOutbound('DRAFT'), true);
    assert.equal(canConfirmPurchaseReturnOutbound('CONFIRMED'), false);
    assert.equal(
      canCreateSupplierRefund(PURCHASE_RETURN_STATUS.waitingRefund, PURCHASE_RETURN_SETTLEMENT.refund),
      true,
    );
    assert.equal(
      canCreateSupplierRefund(PURCHASE_RETURN_STATUS.waitingOutbound, PURCHASE_RETURN_SETTLEMENT.refund),
      false,
    );
    assert.equal(canConfirmSupplierRefund('PENDING'), true);
    assert.equal(canConfirmSupplierRefund('SUCCESS'), false);
    assert.equal(defaultOutboundQuantity(10, 4), 4);
    assert.equal(defaultOutboundQuantity(3, 8), 3);
    assert.equal(purchaseReturnStatusLabel(PURCHASE_RETURN_STATUS.waitingRefund), '待退款');
  });
});
