import type {
  AfterSaleSummary,
  AfterSaleTrendPoint,
  AfterSaleTypeCount,
  AnalyticsOverview,
  ApiResponse,
  InventorySkuRow,
  InventorySummary,
  PendingCounts,
  PurchaseSummary,
  PurchaseTrendPoint,
  SalesSummary,
  SalesTrendPoint,
  StatusCount,
  TopCustomer,
  TopProduct,
  TopSku,
  TopSupplier,
  TransactionTrendPoint,
  TransactionTypePoint,
  WarehouseInventorySummary,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export interface AnalyticsRangeParams {
  startDate?: string;
  endDate?: string;
  warehouseId?: number;
}

function rangeQuery(params: AnalyticsRangeParams) {
  return {
    start_date: params.startDate,
    end_date: params.endDate,
    warehouse_id: params.warehouseId,
  };
}

export function fetchAnalyticsOverview(
  params: AnalyticsRangeParams & { lowStockThreshold?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<AnalyticsOverview>>('/api/v1/analytics/overview', {
      params: { ...rangeQuery(params), low_stock_threshold: params.lowStockThreshold },
      signal,
    }),
  );
}

export function fetchAnalyticsPending(
  params: { warehouseId?: number; lowStockThreshold?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<PendingCounts>>('/api/v1/analytics/pending', {
      params: {
        warehouse_id: params.warehouseId,
        low_stock_threshold: params.lowStockThreshold,
      },
      signal,
    }),
  );
}

export function fetchSalesSummary(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<SalesSummary>>('/api/v1/analytics/sales/summary', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchSalesTrend(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<SalesTrendPoint[]>>('/api/v1/analytics/sales/trend', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchSalesStatus(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<StatusCount[]>>('/api/v1/analytics/sales/status', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchSalesTopSkus(
  params: AnalyticsRangeParams & { limit?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<TopSku[]>>('/api/v1/analytics/sales/top-skus', {
      params: { ...rangeQuery(params), limit: params.limit },
      signal,
    }),
  );
}

export function fetchSalesTopProducts(
  params: AnalyticsRangeParams & { limit?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<TopProduct[]>>('/api/v1/analytics/sales/top-products', {
      params: { ...rangeQuery(params), limit: params.limit },
      signal,
    }),
  );
}

export function fetchSalesTopCustomers(
  params: AnalyticsRangeParams & { limit?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<TopCustomer[]>>('/api/v1/analytics/sales/top-customers', {
      params: { ...rangeQuery(params), limit: params.limit },
      signal,
    }),
  );
}

export function fetchPurchaseSummary(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseSummary>>('/api/v1/analytics/purchases/summary', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchPurchaseTrend(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<PurchaseTrendPoint[]>>('/api/v1/analytics/purchases/trend', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchPurchaseStatus(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<StatusCount[]>>('/api/v1/analytics/purchases/status', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchPurchaseTopSuppliers(
  params: AnalyticsRangeParams & { limit?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<TopSupplier[]>>('/api/v1/analytics/purchases/top-suppliers', {
      params: { ...rangeQuery(params), limit: params.limit },
      signal,
    }),
  );
}

export function fetchInventorySummary(
  params: { warehouseId?: number; lowStockThreshold?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<InventorySummary>>('/api/v1/analytics/inventory/summary', {
      params: {
        warehouse_id: params.warehouseId,
        low_stock_threshold: params.lowStockThreshold,
      },
      signal,
    }),
  );
}

export function fetchInventoryByWarehouse(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<WarehouseInventorySummary[]>>('/api/v1/analytics/inventory/by-warehouse', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchInventoryTopSkus(
  params: { metric?: string; warehouseId?: number; limit?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<InventorySkuRow[]>>('/api/v1/analytics/inventory/top-skus', {
      params: {
        metric: params.metric,
        warehouse_id: params.warehouseId,
        limit: params.limit,
      },
      signal,
    }),
  );
}

export function fetchInventoryLowStock(
  params: { warehouseId?: number; lowStockThreshold?: number; limit?: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<InventorySkuRow[]>>('/api/v1/analytics/inventory/low-stock', {
      params: {
        warehouse_id: params.warehouseId,
        low_stock_threshold: params.lowStockThreshold,
        limit: params.limit,
      },
      signal,
    }),
  );
}

export function fetchInventoryTransactionsTrend(
  params: AnalyticsRangeParams,
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<TransactionTrendPoint[]>>(
      '/api/v1/analytics/inventory/transactions-trend',
      { params: rangeQuery(params), signal },
    ),
  );
}

export function fetchInventoryTransactionsByType(
  params: AnalyticsRangeParams,
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<TransactionTypePoint[]>>(
      '/api/v1/analytics/inventory/transactions-by-type',
      { params: rangeQuery(params), signal },
    ),
  );
}

export function fetchAfterSaleSummary(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<AfterSaleSummary>>('/api/v1/analytics/after-sales/summary', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchAfterSaleTrend(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<AfterSaleTrendPoint[]>>('/api/v1/analytics/after-sales/trend', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

export function fetchAfterSaleTypes(params: AnalyticsRangeParams, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<AfterSaleTypeCount[]>>('/api/v1/analytics/after-sales/types', {
      params: rangeQuery(params),
      signal,
    }),
  );
}

async function downloadCsv(url: string, params: Record<string, unknown>, fallbackName: string) {
  const response = await apiClient.get<Blob>(url, { params, responseType: 'blob' });
  const blob = response.data;
  const disposition = String(response.headers['content-disposition'] ?? '');
  const matched = disposition.match(/filename="?([^"]+)"?/i);
  const filename = matched?.[1] ?? fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export function exportSalesTrendCsv(params: AnalyticsRangeParams) {
  return downloadCsv('/api/v1/analytics/sales/trend.csv', rangeQuery(params), 'sales-trend.csv');
}

export function exportPurchaseTrendCsv(params: AnalyticsRangeParams) {
  return downloadCsv(
    '/api/v1/analytics/purchases/trend.csv',
    rangeQuery(params),
    'purchase-trend.csv',
  );
}

export function exportLowStockCsv(params: { warehouseId?: number; lowStockThreshold?: number }) {
  return downloadCsv(
    '/api/v1/analytics/inventory/low-stock.csv',
    {
      warehouse_id: params.warehouseId,
      low_stock_threshold: params.lowStockThreshold,
    },
    'low-stock.csv',
  );
}
