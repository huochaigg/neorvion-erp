import {
  ANALYTICS_STALE_TIME_MS,
  analyticsQueryKey,
  inventoryTransactionTypeLabel,
  toChartNumber,
  type InventorySkuRow,
  type WarehouseInventorySummary,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Card, Select } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo, useState } from 'react';
import {
  exportLowStockCsv,
  fetchInventoryByWarehouse,
  fetchInventoryLowStock,
  fetchInventorySummary,
  fetchInventoryTopSkus,
  fetchInventoryTransactionsByType,
  fetchInventoryTransactionsTrend,
} from '@/api/analytics';
import { AnalyticsChart } from '@/components/analytics/AnalyticsChart';
import { AnalyticsToolbar } from '@/components/analytics/AnalyticsToolbar';
import { ChartGrid, KpiCard, KpiGrid } from '@/components/analytics/KpiCard';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { defaultAnalyticsRange, rangeToAnalyticsParams } from '@/lib/analytics-range';
import type { PageProps } from '@/router/types';

const THRESHOLDS = [5, 10, 20, 50];

export function InventoryAnalyticsPage(props: PageProps) {
  const { tenantId } = usePermissions();
  const queryClient = useQueryClient();
  const [range, setRange] = useState(defaultAnalyticsRange);
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const [threshold, setThreshold] = useState(10);
  const [metric, setMetric] = useState('reserved');
  const params = { ...rangeToAnalyticsParams(range), warehouseId };
  const enabled = tenantId != null;

  const summary = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'inventory-summary', { warehouseId, threshold }),
    queryFn: ({ signal }) =>
      fetchInventorySummary({ warehouseId, lowStockThreshold: threshold }, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const byWarehouse = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'inventory-by-warehouse', params),
    queryFn: ({ signal }) => fetchInventoryByWarehouse(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const topSkus = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'inventory-top-skus', { warehouseId, metric }),
    queryFn: ({ signal }) => fetchInventoryTopSkus({ metric, warehouseId, limit: 10 }, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const lowStock = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'inventory-low-stock', { warehouseId, threshold }),
    queryFn: ({ signal }) =>
      fetchInventoryLowStock({ warehouseId, lowStockThreshold: threshold, limit: 100 }, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const txTrend = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'inventory-tx-trend', params),
    queryFn: ({ signal }) => fetchInventoryTransactionsTrend(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const txTypes = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'inventory-tx-types', params),
    queryFn: ({ signal }) => fetchInventoryTransactionsByType(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });

  const warehouseOption = useMemo(() => {
    const rows = byWarehouse.data ?? [];
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['实际库存', '预占', '可用'] },
      grid: { left: 48, right: 16, top: 32, bottom: 48 },
      xAxis: { type: 'category', data: rows.map((item) => item.warehouse_name), axisLabel: { rotate: 20 } },
      yAxis: { type: 'value' },
      series: [
        { name: '实际库存', type: 'bar', data: rows.map((item) => item.quantity) },
        { name: '预占', type: 'bar', data: rows.map((item) => item.reserved_quantity) },
        { name: '可用', type: 'bar', data: rows.map((item) => item.available_quantity) },
      ],
    };
  }, [byWarehouse.data]);

  const txOption = useMemo(() => {
    const points = txTrend.data ?? [];
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['入库', '出库', '盘点调整'] },
      grid: { left: 48, right: 16, top: 32, bottom: 32 },
      xAxis: { type: 'category', data: points.map((item) => item.date) },
      yAxis: { type: 'value' },
      series: [
        { name: '入库', type: 'bar', data: points.map((item) => item.inbound_quantity) },
        { name: '出库', type: 'bar', data: points.map((item) => item.outbound_quantity) },
        { name: '盘点调整', type: 'line', data: points.map((item) => toChartNumber(item.adjustment_quantity)) },
      ],
    };
  }, [txTrend.data]);

  const skuColumns: ColumnsType<InventorySkuRow> = [
    { title: 'SKU', dataIndex: 'sku_code', width: 140, render: (value: string) => <CodeCell value={value} /> },
    { title: '商品', dataIndex: 'product_name', width: 160, render: (value: string) => <EllipsisCell value={value} /> },
    { title: '仓库', dataIndex: 'warehouse_name', width: 120, render: (value: string) => <EllipsisCell value={value} /> },
    { title: '实际', dataIndex: 'quantity', width: 80, align: 'right' },
    { title: '预占', dataIndex: 'reserved_quantity', width: 80, align: 'right' },
    { title: '可用', dataIndex: 'available_quantity', width: 80, align: 'right' },
  ];
  const warehouseColumns: ColumnsType<WarehouseInventorySummary> = [
    { title: '仓库', dataIndex: 'warehouse_name', width: 140, render: (value: string) => <EllipsisCell value={value} /> },
    { title: 'SKU 数', dataIndex: 'sku_count', width: 80, align: 'right' },
    { title: '实际', dataIndex: 'quantity', width: 80, align: 'right' },
    { title: '预占', dataIndex: 'reserved_quantity', width: 80, align: 'right' },
    { title: '可用', dataIndex: 'available_quantity', width: 80, align: 'right' },
    { title: '入库', dataIndex: 'inbound_quantity', width: 80, align: 'right' },
    { title: '出库', dataIndex: 'outbound_quantity', width: 80, align: 'right' },
    { title: '调入', dataIndex: 'transfer_in_quantity', width: 80, align: 'right' },
    { title: '调出', dataIndex: 'transfer_out_quantity', width: 80, align: 'right' },
    { title: '盘点差', dataIndex: 'stocktake_adjustment_quantity', width: 80, align: 'right' },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '库存分析'}
        description={props.description ?? '可用库存 = 实际 − 预占。零库存指可用为 0。低库存按阈值比较可用库存。'}
      />
      <AnalyticsToolbar
        range={range}
        onRangeChange={setRange}
        warehouseId={warehouseId}
        onWarehouseChange={setWarehouseId}
        onRefresh={() => {
          void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'analytics'] });
        }}
        extra={
          <>
            <Select
              value={threshold}
              className="min-w-28"
              onChange={setThreshold}
              options={THRESHOLDS.map((item) => ({ value: item, label: `阈值 ${item}` }))}
            />
            <Button onClick={() => void exportLowStockCsv({ warehouseId, lowStockThreshold: threshold })}>
              导出低库存
            </Button>
          </>
        }
      />
      <KpiGrid>
        <KpiCard title="实际库存" value={summary.data?.total_quantity ?? 0} loading={summary.isPending} />
        <KpiCard title="预占库存" value={summary.data?.total_reserved_quantity ?? 0} loading={summary.isPending} />
        <KpiCard title="可用库存" value={summary.data?.total_available_quantity ?? 0} loading={summary.isPending} />
        <KpiCard title="SKU 数" value={summary.data?.sku_count ?? 0} loading={summary.isPending} />
        <KpiCard title="零可用" value={summary.data?.zero_stock_sku_count ?? 0} loading={summary.isPending} hint="available = 0" />
        <KpiCard title="低库存" value={summary.data?.low_stock_sku_count ?? 0} loading={summary.isPending} to="/inventory/list" />
      </KpiGrid>
      <ChartGrid>
        <Card className="mt-4!" title="仓库分布">
          <AnalyticsChart
            option={warehouseOption}
            loading={byWarehouse.isPending}
            error={byWarehouse.error}
            empty={!byWarehouse.isPending && !(byWarehouse.data ?? []).some((item) => item.quantity > 0)}
          />
        </Card>
        <Card className="mt-4!" title="库存流水趋势">
          <AnalyticsChart
            option={txOption}
            loading={txTrend.isPending}
            error={txTrend.error}
            empty={!txTrend.isPending && (txTrend.data?.every((item) => item.inbound_quantity === 0 && item.outbound_quantity === 0) ?? true)}
          />
        </Card>
      </ChartGrid>
      <Card
        className="mt-4!"
        title="库存 Top SKU"
        extra={
          <Select
            value={metric}
            className="min-w-36"
            onChange={setMetric}
            options={[
              { value: 'quantity', label: '库存最高' },
              { value: 'reserved', label: '预占最高' },
              { value: 'available', label: '可用最低' },
            ]}
          />
        }
      >
        <AppTable<InventorySkuRow>
          fillHeight={false}
          rowKey={(row) => `${row.warehouse_id}-${row.sku_id}`}
          columns={skuColumns}
          dataSource={topSkus.data ?? []}
          loading={topSkus.isPending}
          pagination={false}
        />
      </Card>
      <Card className="mt-4!" title="低库存列表">
        <AppTable<InventorySkuRow>
          fillHeight={false}
          rowKey={(row) => `${row.warehouse_id}-${row.sku_id}`}
          columns={skuColumns}
          dataSource={lowStock.data ?? []}
          loading={lowStock.isPending}
          pagination={{ defaultPageSize: 10 }}
        />
      </Card>
      <Card className="mt-4!" title="仓库分析">
        <AppTable<WarehouseInventorySummary>
          fillHeight={false}
          rowKey="warehouse_id"
          columns={warehouseColumns}
          dataSource={byWarehouse.data ?? []}
          loading={byWarehouse.isPending}
          pagination={false}
        />
      </Card>
      <Card className="mt-4!" title="流水类型合计">
        <AppTable
          fillHeight={false}
          rowKey="type"
          columns={[
            {
              title: '类型',
              dataIndex: 'type',
              render: (value: string) => inventoryTransactionTypeLabel(value),
            },
            { title: '数量变动合计', dataIndex: 'quantity', align: 'right' as const },
          ]}
          dataSource={txTypes.data ?? []}
          loading={txTypes.isPending}
          pagination={false}
        />
      </Card>
    </FormPageContainer>
  );
}
