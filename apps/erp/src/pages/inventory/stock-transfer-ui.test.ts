import assert from 'node:assert/strict';
import {
  canAccess,
  canCancelStockTransfer,
  canConfirmTransferOutbound,
  canConfirmTransferReceive,
  canEditStockTransfer,
  canSubmitStockTransfer,
  PERMISSION_CODE,
  STOCK_TRANSFER_STATUS,
  stocktakeQueryKey,
  stockTransferQueryKey,
  stockTransfersQueryKey,
  stockTransferStatusLabel,
  transferStepIndex,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('调拨页 UI 规则', () => {
  it('按钮与后端权限编码一致', () => {
    const viewer = [PERMISSION_CODE.stockTransferRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.stockTransferCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.stockTransferOutbound]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.stockTransferReceive]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.stockTransferRead]), true);
    const warehouse = [
      PERMISSION_CODE.stockTransferRead,
      PERMISSION_CODE.stockTransferOutbound,
      PERMISSION_CODE.stockTransferReceive,
    ];
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.stockTransferOutbound]), true);
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.stockTransferReceive]), true);
  });

  it('草稿可编辑，待调出可确认调出，在途可确认调入且不能取消', () => {
    assert.equal(canEditStockTransfer(STOCK_TRANSFER_STATUS.draft), true);
    assert.equal(canEditStockTransfer(STOCK_TRANSFER_STATUS.pendingOutbound), false);
    assert.equal(canSubmitStockTransfer(STOCK_TRANSFER_STATUS.draft, true), true);
    assert.equal(canConfirmTransferOutbound(STOCK_TRANSFER_STATUS.pendingOutbound), true);
    assert.equal(canConfirmTransferReceive(STOCK_TRANSFER_STATUS.inTransit), true);
    assert.equal(canCancelStockTransfer(STOCK_TRANSFER_STATUS.inTransit), false);
    assert.equal(canCancelStockTransfer(STOCK_TRANSFER_STATUS.pendingOutbound), true);
    assert.equal(stockTransferStatusLabel(STOCK_TRANSFER_STATUS.inTransit), '运输中');
    assert.equal(transferStepIndex(STOCK_TRANSFER_STATUS.inTransit), 2);
    assert.equal(transferStepIndex(STOCK_TRANSFER_STATUS.completed), 3);
  });

  it('Query Key 含 tenantId，调拨与盘点互不串扰', () => {
    assert.notDeepEqual(stockTransfersQueryKey(1), stockTransfersQueryKey(2));
    assert.notDeepEqual(
      stockTransfersQueryKey(1, { status: 'DRAFT' }),
      stockTransfersQueryKey(1, { status: 'IN_TRANSIT' }),
    );
    assert.notDeepEqual(stockTransferQueryKey(1, 8), stockTransferQueryKey(2, 8));
    assert.notDeepEqual(stockTransferQueryKey(1, 8), stocktakeQueryKey(1, 8));
  });
});
