import {
  ANALYTICS_STALE_TIME_MS,
  analyticsQueryKey,
  formatAnalyticsAmount,
  purchaseOrderStatusLabel,
  toChartNumber,
  type PurchaseTrendPoint,
  type TopSupplier,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button, Card } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo, useState } from 'react';
import {
  exportPurchaseTrendCsv,
  fetchPurchaseStatus,
  fetchPurchaseSummary,
  fetchPurchaseTopSuppliers,
  fetchPurchaseTrend,
} from '@/api/analytics';
import { AnalyticsChart } from '@/components/analytics/AnalyticsChart';
import { AnalyticsToolbar } from '@/components/analytics/AnalyticsToolbar';
import { ChartGrid, KpiCard, KpiGrid } from '@/components/analytics/KpiCard';
import { AppTable, EllipsisCell } from '@/components/AppTable';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { defaultAnalyticsRange, rangeToAnalyticsParams } from '@/lib/analytics-range';
import { statusPieOption } from '@/components/analytics/chart-options';
import type { PageProps } from '@/router/types';

export function PurchaseAnalyticsPage(props: PageProps) {
  const { tenantId } = usePermissions();
  const queryClient = useQueryClient();
  const [range, setRange] = useState(defaultAnalyticsRange);
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const params = { ...rangeToAnalyticsParams(range), warehouseId };
  const enabled = tenantId != null;

  const summary = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'purchase-summary', params),
    queryFn: ({ signal }) => fetchPurchaseSummary(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const trend = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'purchase-trend', params),
    queryFn: ({ signal }) => fetchPurchaseTrend(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const status = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'purchase-status', params),
    queryFn: ({ signal }) => fetchPurchaseStatus(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const suppliers = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'purchase-top-suppliers', params),
    queryFn: ({ signal }) => fetchPurchaseTopSuppliers({ ...params, limit: 10 }, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });

  const trendOption = useMemo(() => {
    const points = trend.data ?? [];
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['采购额', '收货数量', '退货出库'] },
      grid: { left: 48, right: 24, top: 32, bottom: 32 },
      xAxis: { type: 'category', data: points.map((item) => item.date) },
      yAxis: [
        { type: 'value', name: '金额' },
        { type: 'value', name: '数量' },
      ],
      series: [
        { name: '采购额', type: 'line', data: points.map((item) => toChartNumber(item.purchase_amount)) },
        { name: '收货数量', type: 'bar', yAxisIndex: 1, data: points.map((item) => item.received_quantity) },
        {
          name: '退货出库',
          type: 'bar',
          yAxisIndex: 1,
          data: points.map((item) => item.purchase_return_quantity),
        },
      ],
    };
  }, [trend.data]);

  const supplierColumns: ColumnsType<TopSupplier> = [
    { title: '供应商', dataIndex: 'supplier_name', width: 180, render: (value: string) => <EllipsisCell value={value} /> },
    { title: '采购单数', dataIndex: 'purchase_order_count', width: 90, align: 'right' },
    {
      title: '采购额',
      dataIndex: 'purchase_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
    { title: '收货数量', dataIndex: 'received_quantity', width: 90, align: 'right' },
    { title: '退货出库', dataIndex: 'purchase_return_quantity', width: 90, align: 'right' },
  ];
  const dayColumns: ColumnsType<PurchaseTrendPoint> = [
    { title: '日期', dataIndex: 'date', width: 120 },
    { title: '采购单数', dataIndex: 'purchase_order_count', width: 90, align: 'right' },
    {
      title: '采购额',
      dataIndex: 'purchase_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
    { title: '收货数量', dataIndex: 'received_quantity', width: 90, align: 'right' },
    { title: '退货出库', dataIndex: 'purchase_return_quantity', width: 90, align: 'right' },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '采购分析'}
        description={props.description ?? '有效采购单排除草稿、驳回与取消。收货数量按确认收货时间。'}
      />
      <AnalyticsToolbar
        range={range}
        onRangeChange={setRange}
        warehouseId={warehouseId}
        onWarehouseChange={setWarehouseId}
        onRefresh={() => {
          void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'analytics'] });
        }}
        extra={<Button onClick={() => void exportPurchaseTrendCsv(params)}>导出按日汇总</Button>}
      />
      <KpiGrid>
        <KpiCard title="采购额" value={formatAnalyticsAmount(summary.data?.purchase_amount)} loading={summary.isPending} />
        <KpiCard title="有效采购单" value={summary.data?.purchase_order_count ?? 0} loading={summary.isPending} />
        <KpiCard title="收货数量" value={summary.data?.received_quantity ?? 0} loading={summary.isPending} />
        <KpiCard title="待收货单" value={summary.data?.pending_receipt_order_count ?? 0} loading={summary.isPending} hint="当前快照" to="/purchases/list" />
        <KpiCard title="采购退货单" value={summary.data?.purchase_return_order_count ?? 0} loading={summary.isPending} />
        <KpiCard title="供应商退款" value={formatAnalyticsAmount(summary.data?.supplier_refund_amount)} loading={summary.isPending} hint="仅 SUCCESS" />
      </KpiGrid>
      <ChartGrid>
        <Card className="mt-4!" title="采购趋势">
          <AnalyticsChart
            option={trendOption}
            loading={trend.isPending}
            error={trend.error}
            empty={!trend.isPending && (trend.data?.every((item) => item.purchase_order_count === 0) ?? true)}
          />
        </Card>
        <Card className="mt-4!" title="采购状态">
          <AnalyticsChart
            option={statusPieOption(status.data ?? [], purchaseOrderStatusLabel)}
            loading={status.isPending}
            error={status.error}
            empty={!status.isPending && !(status.data ?? []).some((item) => item.count > 0)}
          />
        </Card>
      </ChartGrid>
      <Card className="mt-4!" title="Top 供应商">
        <AppTable<TopSupplier>
          fillHeight={false}
          rowKey="supplier_id"
          columns={supplierColumns}
          dataSource={suppliers.data ?? []}
          loading={suppliers.isPending}
          pagination={false}
        />
      </Card>
      <Card className="mt-4!" title="按日汇总">
        <AppTable<PurchaseTrendPoint>
          fillHeight={false}
          rowKey="date"
          columns={dayColumns}
          dataSource={trend.data ?? []}
          loading={trend.isPending}
          pagination={{ defaultPageSize: 10 }}
        />
      </Card>
    </FormPageContainer>
  );
}
