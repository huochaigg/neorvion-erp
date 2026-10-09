import assert from 'node:assert/strict';
import {
  canAccess,
  canAddTrackingEvent,
  canCancelShipment,
  canConfirmShipment,
  canCreateShipmentFromOutbound,
  canDeliverShipment,
  canEditShipment,
  carrierQueryKey,
  carriersQueryKey,
  PERMISSION_CODE,
  shipmentQueryKey,
  shipmentStatusLabel,
  shipmentsQueryKey,
  SHIPMENT_STATUS,
} from '@neorvion/shared';
import { describe, it } from 'vitest';

describe('物流商与物流单 UI 规则', () => {
  it('物流商按钮与后端权限编码一致', () => {
    const viewer = [PERMISSION_CODE.carrierRead];
    assert.equal(canAccess(viewer, [PERMISSION_CODE.carrierCreate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.carrierUpdate]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.carrierDisable]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.carrierDelete]), false);
    assert.equal(canAccess(viewer, [PERMISSION_CODE.carrierRead]), true);
  });

  it('物流单操作按状态显示，发货后不能改数量', () => {
    assert.equal(canEditShipment(SHIPMENT_STATUS.draft), true);
    assert.equal(canConfirmShipment(SHIPMENT_STATUS.draft), true);
    assert.equal(canCancelShipment(SHIPMENT_STATUS.draft), true);
    assert.equal(canEditShipment(SHIPMENT_STATUS.shipped), false);
    assert.equal(canConfirmShipment(SHIPMENT_STATUS.shipped), false);
    assert.equal(canCancelShipment(SHIPMENT_STATUS.shipped), false);
    assert.equal(canAddTrackingEvent(SHIPMENT_STATUS.shipped), true);
    assert.equal(canAddTrackingEvent(SHIPMENT_STATUS.inTransit), true);
    assert.equal(canAddTrackingEvent(SHIPMENT_STATUS.draft), false);
    assert.equal(canDeliverShipment(SHIPMENT_STATUS.shipped), true);
    assert.equal(canDeliverShipment(SHIPMENT_STATUS.inTransit), true);
    assert.equal(canDeliverShipment(SHIPMENT_STATUS.delivered), false);
    assert.equal(canCreateShipmentFromOutbound('CONFIRMED', 4), true);
    assert.equal(canCreateShipmentFromOutbound('CONFIRMED', 0), false);
    assert.equal(canCreateShipmentFromOutbound('PICKED', 4), false);
    assert.equal(shipmentStatusLabel(SHIPMENT_STATUS.draft), '草稿');
    assert.equal(shipmentStatusLabel(SHIPMENT_STATUS.shipped), '已发货');
    assert.equal(shipmentStatusLabel(SHIPMENT_STATUS.inTransit), '运输中');
    assert.equal(shipmentStatusLabel(SHIPMENT_STATUS.delivered), '已签收');
  });

  it('运营可确认发货和签收，仓库默认可创建和确认', () => {
    const operator = [
      PERMISSION_CODE.shipmentRead,
      PERMISSION_CODE.shipmentCreate,
      PERMISSION_CODE.shipmentUpdate,
      PERMISSION_CODE.shipmentConfirm,
      PERMISSION_CODE.shipmentTrackingUpdate,
      PERMISSION_CODE.shipmentDeliver,
    ];
    assert.equal(canAccess(operator, [PERMISSION_CODE.shipmentConfirm]), true);
    assert.equal(canAccess(operator, [PERMISSION_CODE.shipmentDeliver]), true);
    assert.equal(canAccess(operator, [PERMISSION_CODE.carrierDelete]), false);
    const warehouse = [
      PERMISSION_CODE.shipmentRead,
      PERMISSION_CODE.shipmentCreate,
      PERMISSION_CODE.shipmentConfirm,
    ];
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.shipmentCreate]), true);
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.shipmentConfirm]), true);
    assert.equal(canAccess(warehouse, [PERMISSION_CODE.shipmentDeliver]), false);
  });

  it('Query Key 含 tenantId，物流单、出库单、销售订单互不串扰', () => {
    assert.notDeepEqual(carriersQueryKey(1), carriersQueryKey(2));
    assert.notDeepEqual(carrierQueryKey(1, 3), carrierQueryKey(2, 3));
    assert.notDeepEqual(shipmentsQueryKey(1), shipmentsQueryKey(2));
    assert.notDeepEqual(
      shipmentsQueryKey(1, { status: 'DRAFT', page: 1 }),
      shipmentsQueryKey(1, { status: 'SHIPPED', page: 1 }),
    );
    assert.notDeepEqual(shipmentQueryKey(1, 8), shipmentQueryKey(2, 8));
  });
});
