/** 与后端物流商 / 物流单 Schema 对齐。确认发货不再扣库存。 */

export const CARRIER_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const CARRIER_TYPE = {
  domesticExpress: 'DOMESTIC_EXPRESS',
  internationalExpress: 'INTERNATIONAL_EXPRESS',
  freightForwarder: 'FREIGHT_FORWARDER',
  platformLogistics: 'PLATFORM_LOGISTICS',
  other: 'OTHER',
} as const;

export const CARRIER_TYPE_LABEL: Record<string, string> = {
  DOMESTIC_EXPRESS: '国内快递',
  INTERNATIONAL_EXPRESS: '国际快递',
  FREIGHT_FORWARDER: '货代',
  PLATFORM_LOGISTICS: '平台物流',
  OTHER: '其他',
};

export const CARRIER_TYPE_OPTIONS = [
  { value: CARRIER_TYPE.domesticExpress, label: '国内快递' },
  { value: CARRIER_TYPE.internationalExpress, label: '国际快递' },
  { value: CARRIER_TYPE.freightForwarder, label: '货代' },
  { value: CARRIER_TYPE.platformLogistics, label: '平台物流' },
  { value: CARRIER_TYPE.other, label: '其他' },
];

export const SHIPMENT_STATUS = {
  draft: 'DRAFT',
  shipped: 'SHIPPED',
  inTransit: 'IN_TRANSIT',
  delivered: 'DELIVERED',
  cancelled: 'CANCELLED',
} as const;

export const SHIPMENT_STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  SHIPPED: '已发货',
  IN_TRANSIT: '运输中',
  DELIVERED: '已签收',
  CANCELLED: '已取消',
};

export const SHIPMENT_STATUS_OPTIONS = [
  { value: SHIPMENT_STATUS.draft, label: '草稿' },
  { value: SHIPMENT_STATUS.shipped, label: '已发货' },
  { value: SHIPMENT_STATUS.inTransit, label: '运输中' },
  { value: SHIPMENT_STATUS.delivered, label: '已签收' },
  { value: SHIPMENT_STATUS.cancelled, label: '已取消' },
];

export const TRACKING_EVENT_STATUS = {
  pickedUp: 'PICKED_UP',
  inTransit: 'IN_TRANSIT',
  arrivedAtHub: 'ARRIVED_AT_HUB',
  outForDelivery: 'OUT_FOR_DELIVERY',
  delivered: 'DELIVERED',
  exception: 'EXCEPTION',
  other: 'OTHER',
} as const;

export const TRACKING_EVENT_STATUS_LABEL: Record<string, string> = {
  PICKED_UP: '已揽收',
  IN_TRANSIT: '运输中',
  ARRIVED_AT_HUB: '到达转运中心',
  OUT_FOR_DELIVERY: '派送中',
  DELIVERED: '已签收',
  EXCEPTION: '异常',
  OTHER: '其他',
};

export const TRACKING_EVENT_STATUS_OPTIONS = [
  { value: TRACKING_EVENT_STATUS.pickedUp, label: '已揽收' },
  { value: TRACKING_EVENT_STATUS.inTransit, label: '运输中' },
  { value: TRACKING_EVENT_STATUS.arrivedAtHub, label: '到达转运中心' },
  { value: TRACKING_EVENT_STATUS.outForDelivery, label: '派送中' },
  { value: TRACKING_EVENT_STATUS.exception, label: '异常' },
  { value: TRACKING_EVENT_STATUS.other, label: '其他' },
];

export function carrierTypeLabel(value: string): string {
  return CARRIER_TYPE_LABEL[value] ?? value;
}

export function shipmentStatusLabel(status: string): string {
  return SHIPMENT_STATUS_LABEL[status] ?? status;
}

export function trackingEventStatusLabel(status: string): string {
  return TRACKING_EVENT_STATUS_LABEL[status] ?? status;
}

export function canEditShipment(status: string): boolean {
  return status === SHIPMENT_STATUS.draft;
}

export function canConfirmShipment(status: string): boolean {
  return status === SHIPMENT_STATUS.draft;
}

export function canCancelShipment(status: string): boolean {
  return status === SHIPMENT_STATUS.draft;
}

export function canAddTrackingEvent(status: string): boolean {
  return status === SHIPMENT_STATUS.shipped || status === SHIPMENT_STATUS.inTransit;
}

export function canDeliverShipment(status: string): boolean {
  return status === SHIPMENT_STATUS.shipped || status === SHIPMENT_STATUS.inTransit;
}

export function canCreateShipmentFromOutbound(status: string, remaining: number): boolean {
  return status === 'CONFIRMED' && remaining > 0;
}

export interface Carrier {
  id: number;
  tenant_id: number;
  name: string;
  code: string;
  carrier_type: string;
  contact_name: string | null;
  contact_phone: string | null;
  website: string | null;
  status: string;
  remark: string | null;
  created_at: string;
  updated_at: string;
}

export interface CarrierList {
  items: Carrier[];
  total: number;
  page: number;
  page_size: number;
}

export interface CarrierCreatePayload {
  name: string;
  code?: string | null;
  carrier_type: string;
  contact_name?: string | null;
  contact_phone?: string | null;
  website?: string | null;
  remark?: string | null;
}

export interface CarrierUpdatePayload {
  name?: string;
  carrier_type?: string;
  contact_name?: string | null;
  contact_phone?: string | null;
  website?: string | null;
  remark?: string | null;
}

export interface ShipmentItem {
  id: number;
  outbound_order_item_id: number;
  sales_order_item_id: number;
  sku_id: number;
  sku_code: string;
  sku_name: string;
  product_name: string;
  quantity: number;
  outbound_quantity: number;
  shipped_before: number;
}

export interface ShipmentTrackingEvent {
  id: number;
  status: string;
  description: string;
  location: string | null;
  occurred_at: string;
  created_by: number | null;
  created_at: string;
}

export interface ShipmentListItem {
  id: number;
  shipment_no: string;
  sales_order_id: number;
  sales_order_no: string;
  outbound_order_id: number;
  outbound_no: string;
  customer_name: string;
  carrier_name: string;
  tracking_no: string | null;
  status: string;
  sku_count: number;
  total_quantity: number;
  shipped_at: string | null;
  delivered_at: string | null;
  created_at: string;
}

export interface ShipmentDetail extends ShipmentListItem {
  recipient_name: string | null;
  address: string | null;
  carrier_id: number;
  remark: string | null;
  shipped_by: number | null;
  shipped_by_name: string | null;
  created_by: number;
  items: ShipmentItem[];
  tracking_events: ShipmentTrackingEvent[];
}

export interface ShipmentList {
  items: ShipmentListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ShipmentCreatePayload {
  outbound_order_id: number;
  carrier_id: number;
  tracking_no?: string | null;
  remark?: string | null;
  items?: Array<{ outbound_order_item_id: number; quantity: number }>;
}

export interface ShipmentUpdatePayload {
  carrier_id?: number;
  tracking_no?: string | null;
  remark?: string | null;
  items?: Array<{ outbound_order_item_id: number; quantity: number }>;
}

export interface TrackingEventCreatePayload {
  status: string;
  description: string;
  location?: string | null;
  occurred_at: string;
}

export interface ShipmentDeliverPayload {
  delivered_at?: string | null;
  remark?: string | null;
}
