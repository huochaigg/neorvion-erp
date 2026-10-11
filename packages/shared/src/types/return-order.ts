/** 与后端退货单 Schema 对齐。收到退货不等于入库；只有 GOOD 进入普通库存。 */

export const RETURN_ORDER_STATUS = {
  waitingReturn: 'WAITING_RETURN',
  partiallyReceived: 'PARTIALLY_RECEIVED',
  received: 'RECEIVED',
  partiallyInbounded: 'PARTIALLY_INBOUNDED',
  inbounded: 'INBOUNDED',
  cancelled: 'CANCELLED',
} as const;

export const RETURN_ORDER_STATUS_LABEL: Record<string, string> = {
  WAITING_RETURN: '待退货',
  PARTIALLY_RECEIVED: '部分收货',
  RECEIVED: '已收货',
  PARTIALLY_INBOUNDED: '部分入库',
  INBOUNDED: '已入库',
  CANCELLED: '已取消',
};

export const RETURN_ORDER_STATUS_OPTIONS = [
  { value: RETURN_ORDER_STATUS.waitingReturn, label: '待退货' },
  { value: RETURN_ORDER_STATUS.partiallyReceived, label: '部分收货' },
  { value: RETURN_ORDER_STATUS.received, label: '已收货' },
  { value: RETURN_ORDER_STATUS.partiallyInbounded, label: '部分入库' },
  { value: RETURN_ORDER_STATUS.inbounded, label: '已入库' },
  { value: RETURN_ORDER_STATUS.cancelled, label: '已取消' },
];

export const RETURN_CONDITION = {
  good: 'GOOD',
  damaged: 'DAMAGED',
  unsellable: 'UNSELLABLE',
  other: 'OTHER',
} as const;

export const RETURN_CONDITION_LABEL: Record<string, string> = {
  GOOD: '正常',
  DAMAGED: '损坏',
  UNSELLABLE: '不可销售',
  OTHER: '其他',
};

export const RETURN_CONDITION_OPTIONS = [
  { value: RETURN_CONDITION.good, label: '正常' },
  { value: RETURN_CONDITION.damaged, label: '损坏' },
  { value: RETURN_CONDITION.unsellable, label: '不可销售' },
  { value: RETURN_CONDITION.other, label: '其他' },
];

export function returnOrderStatusLabel(status: string): string {
  return RETURN_ORDER_STATUS_LABEL[status] ?? status;
}

export function returnConditionLabel(condition: string): string {
  return RETURN_CONDITION_LABEL[condition] ?? condition;
}

/** 仍可能继续登记实收：待退货 / 部分收货 / 部分入库（未收满时）。已收货表示已收满，不能再收。 */
export function canReceiveReturn(status: string): boolean {
  return (
    status === RETURN_ORDER_STATUS.waitingReturn ||
    status === RETURN_ORDER_STATUS.partiallyReceived ||
    status === RETURN_ORDER_STATUS.partiallyInbounded
  );
}

/** 收货完成前后都可改物流信息；已入库 / 已取消不可改。 */
export function canUpdateReturnLogistics(status: string): boolean {
  return (
    canReceiveReturn(status) ||
    status === RETURN_ORDER_STATUS.received
  );
}

export function canConfirmReturnInbound(status: string, receivedQuantity: number): boolean {
  return (
    receivedQuantity > 0 &&
    (status === RETURN_ORDER_STATUS.partiallyReceived ||
      status === RETURN_ORDER_STATUS.received ||
      status === RETURN_ORDER_STATUS.partiallyInbounded)
  );
}

export function defaultInboundQuantity(condition: string, receivedQuantity: number): number {
  return condition === RETURN_CONDITION.good ? receivedQuantity : 0;
}

export interface ReturnOrderItem {
  id: number;
  after_sale_item_id: number;
  sales_order_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  spec_values: Record<string, unknown>;
  expected_quantity: number;
  received_quantity: number;
  inbound_quantity: number;
  condition: string;
  remark: string | null;
}

export interface ReturnOrderDetail {
  id: number;
  return_no: string;
  after_sale_order_id: number;
  after_sale_no: string;
  sales_order_id: number;
  sales_order_no: string;
  customer_id: number;
  customer_name: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  tracking_no: string | null;
  carrier_name: string | null;
  remark: string | null;
  expected_quantity: number;
  received_quantity: number;
  inbound_quantity: number;
  received_at: string | null;
  received_by: number | null;
  received_by_name: string | null;
  confirmed_at: string | null;
  confirmed_by: number | null;
  confirmed_by_name: string | null;
  created_at: string;
  updated_at: string;
  items: ReturnOrderItem[];
}

export interface ReturnOrderListItem {
  id: number;
  return_no: string;
  after_sale_order_id: number;
  after_sale_no: string;
  sales_order_id: number;
  sales_order_no: string;
  customer_name: string;
  warehouse_name: string;
  status: string;
  expected_quantity: number;
  received_quantity: number;
  inbound_quantity: number;
  created_at: string;
}

export interface ReturnOrderList {
  items: ReturnOrderListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReturnReceiveItemInput {
  item_id: number;
  received_quantity: number;
  condition: string;
  remark?: string | null;
}

export interface ReturnReceivePayload {
  items: ReturnReceiveItemInput[];
}

export interface ReturnOrderUpdatePayload {
  tracking_no?: string | null;
  carrier_name?: string | null;
  remark?: string | null;
}
