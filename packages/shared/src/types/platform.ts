export const EVENT_SEVERITY = {
  info: 'INFO',
  warning: 'WARNING',
  error: 'ERROR',
  critical: 'CRITICAL',
} as const;

export const EVENT_SEVERITY_LABEL: Record<string, string> = {
  INFO: '信息',
  WARNING: '警告',
  ERROR: '错误',
  CRITICAL: '严重',
};

export const EVENT_STATUS_LABEL: Record<string, string> = {
  PENDING: '待处理',
  PROCESSING: '处理中',
  PROCESSED: '已处理',
  FAILED: '失败',
};

export const TASK_STATUS = {
  pending: 'PENDING',
  queued: 'QUEUED',
  running: 'RUNNING',
  success: 'SUCCESS',
  failed: 'FAILED',
  cancelled: 'CANCELLED',
} as const;

export const TASK_STATUS_LABEL: Record<string, string> = {
  PENDING: '等待创建',
  QUEUED: '排队中',
  RUNNING: '执行中',
  SUCCESS: '成功',
  FAILED: '失败',
  CANCELLED: '已取消',
};

export const OPERATION_RESULT_LABEL: Record<string, string> = {
  SUCCESS: '成功',
  FAILED: '失败',
};

export interface SystemEvent {
  id: number;
  event_id: string;
  event_type: string;
  event_source: string;
  aggregate_type: string;
  aggregate_id: number | null;
  reference_type: string | null;
  reference_id: number | null;
  severity: string;
  title: string;
  message: string | null;
  payload: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  status: string;
  retry_count: number;
  last_error: string | null;
  occurred_at: string;
  processed_at: string | null;
  created_at: string;
}

export interface SystemEventList {
  items: SystemEvent[];
  total: number;
  page: number;
  page_size: number;
}

export interface OperationLog {
  id: number;
  tenant_id: number | null;
  operator_user_id: number | null;
  action: string;
  module: string;
  resource_type: string | null;
  resource_id: number | null;
  resource_name: string | null;
  request_method: string | null;
  request_path: string | null;
  request_id: string | null;
  result: string;
  error_code: string | null;
  description: string | null;
  metadata: Record<string, unknown> | null;
  occurred_at: string;
}

export interface OperationLogList {
  items: OperationLog[];
  total: number;
  page: number;
  page_size: number;
}

export interface AsyncTask {
  id: number;
  task_id: string;
  task_type: string;
  status: string;
  progress: number;
  title: string;
  description: string | null;
  payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
  created_by: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  queued?: boolean | null;
}

export interface AsyncTaskList {
  items: AsyncTask[];
  total: number;
  page: number;
  page_size: number;
}

export interface AsyncTaskLog {
  id: number;
  task_id: string;
  level: string;
  message: string;
  created_at: string;
}

const AGGREGATE_PATH: Record<string, (id: number) => string> = {
  SALES_ORDER: (id) => `/orders/${id}`,
  PURCHASE_ORDER: (id) => `/purchases/${id}`,
  PURCHASE_RECEIPT: (id) => `/purchase-receipts/${id}`,
  OUTBOUND_ORDER: (id) => `/outbound-orders/${id}`,
  INVENTORY: (id) => `/inventory/${id}`,
  STOCK_TRANSFER: (id) => `/stock-transfers/${id}`,
  SHIPMENT: (id) => `/shipments/${id}`,
  AFTER_SALE: (id) => `/after-sales/${id}`,
  REFUND: () => `/refunds`,
  PURCHASE_RETURN: (id) => `/purchase-returns/${id}`,
};

export function eventBusinessPath(
  aggregateType: string,
  aggregateId: number | null,
): string | null {
  if (aggregateId == null) {
    return null;
  }
  const factory = AGGREGATE_PATH[aggregateType];
  return factory ? factory(aggregateId) : null;
}

export function eventSeverityLabel(value: string) {
  return EVENT_SEVERITY_LABEL[value] ?? value;
}

export function taskStatusLabel(value: string) {
  return TASK_STATUS_LABEL[value] ?? value;
}
