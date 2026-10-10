import assert from 'node:assert/strict';
import {
  canAccess,
  canCancelStocktake,
  canConfirmStocktake,
  canEditStocktakeCount,
  canSubmitStocktake,
  PERMISSION_CODE,
  STOCKTAKE_STATUS,
  stocktakeDifference,
  stocktakeDifferenceText,
  stocktakeQueryKey,
  stocktakesQueryKey,
  stocktakeStatusLabel,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('盘点页 UI 规则', () => {
  it('按钮与后端权限编码一致', () => {
    const viewer = [PERMISSION_CODE.stocktakeRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.stocktakeCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.stocktakeConfirm]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.stocktakeRead]), true);
    const warehouse = [
      PERMISSION_CODE.stocktakeRead,
      PERMISSION_CODE.stocktakeCreate,
      PERMISSION_CODE.stocktakeUpdate,
      PERMISSION_CODE.stocktakeSubmit,
      PERMISSION_CODE.stocktakeConfirm,
    ];
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.stocktakeConfirm]), true);
  });

  it('盘点中可录入，提交后只读，确认后不可取消', () => {
    assert.equal(canEditStocktakeCount(STOCKTAKE_STATUS.counting), true);
    assert.equal(canEditStocktakeCount(STOCKTAKE_STATUS.pendingConfirmation), false);
    assert.equal(canSubmitStocktake(STOCKTAKE_STATUS.counting, true), true);
    assert.equal(canSubmitStocktake(STOCKTAKE_STATUS.counting, false), false);
    assert.equal(canConfirmStocktake(STOCKTAKE_STATUS.pendingConfirmation), true);
    assert.equal(canCancelStocktake(STOCKTAKE_STATUS.confirmed), false);
    assert.equal(canCancelStocktake(STOCKTAKE_STATUS.counting), true);
    assert.equal(stocktakeStatusLabel(STOCKTAKE_STATUS.counting), '盘点中');
  });

  it('差异同时给出盘盈盘亏文本，不只靠颜色', () => {
    assert.equal(stocktakeDifference(98, 100), -2);
    assert.equal(stocktakeDifferenceText(5), '盘盈 5');
    assert.equal(stocktakeDifferenceText(-3), '盘亏 3');
    assert.equal(stocktakeDifferenceText(0), '一致');
    assert.equal(stocktakeDifferenceText(null), '未盘');
  });

  it('Query Key 含 tenantId，切租户不会复用盘点缓存', () => {
    assert.notDeepEqual(stocktakesQueryKey(1), stocktakesQueryKey(2));
    assert.notDeepEqual(
      stocktakesQueryKey(1, { status: 'COUNTING' }),
      stocktakesQueryKey(1, { status: 'CONFIRMED' }),
    );
    assert.notDeepEqual(stocktakeQueryKey(1, 9), stocktakeQueryKey(2, 9));
  });
});
