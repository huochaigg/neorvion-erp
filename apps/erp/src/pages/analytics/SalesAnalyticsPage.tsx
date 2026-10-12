import {
  ANALYTICS_STALE_TIME_MS,
  analyticsQueryKey,
  formatAnalyticsAmount,
  formatAnalyticsRate,
  salesOrderStatusLabel,
  specValuesLabel,
  type SalesTrendPoint,
  type TopCustomer,
  type TopSku,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo, useState } from 'react';
import { createSalesExportTask } from '@/api/tasks';
import {
  exportSalesTrendCsv,
  fetchSalesStatus,
  fetchSalesSummary,
  fetchSalesTopCustomers,
  fetchSalesTopSkus,
  fetchSalesTrend,
} from '@/api/analytics';
import { AnalyticsChart } from '@/components/analytics/AnalyticsChart';
import { AnalyticsToolbar } from '@/components/analytics/AnalyticsToolbar';
import { ChartGrid, KpiCard, KpiGrid } from '@/components/analytics/KpiCard';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { salesTrendOption, statusPieOption } from '@/components/analytics/chart-options';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { defaultAnalyticsRange, rangeToAnalyticsParams } from '@/lib/analytics-range';
import type { PageProps } from '@/router/types';

export function SalesAnalyticsPage(props: PageProps) {
  const { message } = App.useApp();
  const { tenantId } = usePermissions();
  const queryClient = useQueryClient();
  const [range, setRange] = useState(defaultAnalyticsRange);
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const params = { ...rangeToAnalyticsParams(range), warehouseId };
  const filters = { ...params };
  const enabled = tenantId != null;

  const summary = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'sales-summary', filters),
    queryFn: ({ signal }) => fetchSalesSummary(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const trend = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'sales-trend', filters),
    queryFn: ({ signal }) => fetchSalesTrend(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const status = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'sales-status', filters),
    queryFn: ({ signal }) => fetchSalesStatus(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const topSkus = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'sales-top-skus', filters),
    queryFn: ({ signal }) => fetchSalesTopSkus({ ...params, limit: 10 }, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const topCustomers = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'sales-top-customers', filters),
    queryFn: ({ signal }) => fetchSalesTopCustomers({ ...params, limit: 10 }, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });

  const trendOption = useMemo(
    () => salesTrendOption(trend.data ?? []),
    [trend.data],
  );
  const statusOption = useMemo(
    () => statusPieOption(status.data ?? [], salesOrderStatusLabel),
    [status.data],
  );

  const skuColumns: ColumnsType<TopSku> = [
    { title: 'SKU', dataIndex: 'sku_code', width: 140, render: (value: string) => <CodeCell value={value} /> },
    { title: '商品', dataIndex: 'product_name', width: 160, render: (value: string) => <EllipsisCell value={value} /> },
    {
      title: '规格',
      dataIndex: 'spec_values',
      width: 140,
      render: (value: Record<string, unknown>) => <EllipsisCell value={specValuesLabel(value)} />,
    },
    { title: '销量', dataIndex: 'sales_quantity', width: 80, align: 'right' },
    {
      title: '销售额',
      dataIndex: 'sales_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
    { title: '订单数', dataIndex: 'order_count', width: 80, align: 'right' },
  ];
  const customerColumns: ColumnsType<TopCustomer> = [
    { title: '客户', dataIndex: 'customer_name', width: 160, render: (value: string) => <EllipsisCell value={value} /> },
    { title: '订单数', dataIndex: 'order_count', width: 80, align: 'right' },
    {
      title: '销售额',
      dataIndex: 'sales_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
    {
      title: '退款',
      dataIndex: 'refund_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
    {
      title: '净销售',
      dataIndex: 'net_sales_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
  ];
  const dayColumns: ColumnsType<SalesTrendPoint> = [
    { title: '日期', dataIndex: 'date', width: 120 },
    { title: '订单数', dataIndex: 'order_count', width: 90, align: 'right' },
    {
      title: '销售额',
      dataIndex: 'sales_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
    {
      title: '退款',
      dataIndex: 'refund_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '销售分析'}
        description={props.description ?? '有效销售订单排除草稿与取消。净销售额扣减成功退款。'}
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
            <Button onClick={() => void exportSalesTrendCsv(params)}>同步导出</Button>
            <Button
              onClick={() => {
                void createSalesExportTask(params)
                  .then(() => message.success('已创建异步导出任务，请到任务中心查看'))
                  .catch(() => message.error('创建导出任务失败'));
              }}
            >
              异步导出
            </Button>
          </>
        }
      />
      <KpiGrid>
        <KpiCard title="销售额" value={formatAnalyticsAmount(summary.data?.gross_sales_amount)} loading={summary.isPending} hint="有效订单金额" />
        <KpiCard title="净销售额" value={formatAnalyticsAmount(summary.data?.net_sales_amount)} loading={summary.isPending} hint="扣成功退款" />
        <KpiCard title="有效订单" value={summary.data?.order_count ?? 0} loading={summary.isPending} />
        <KpiCard title="客单价" value={formatAnalyticsAmount(summary.data?.average_order_value)} loading={summary.isPending} />
        <KpiCard title="成功退款" value={formatAnalyticsAmount(summary.data?.refund_amount)} loading={summary.isPending} />
        <KpiCard title="售后率" value={formatAnalyticsRate(summary.data?.return_rate)} loading={summary.isPending} hint="去重订单数 ÷ 有效订单" />
      </KpiGrid>
      <ChartGrid>
        <Card className="mt-4!" title="销售趋势">
          <AnalyticsChart
            option={trendOption}
            loading={trend.isPending}
            error={trend.error}
            empty={!trend.isPending && (trend.data?.every((item) => item.order_count === 0 && item.sales_amount === 0) ?? true)}
          />
        </Card>
        <Card className="mt-4!" title="订单状态">
          <AnalyticsChart
            option={statusOption}
            loading={status.isPending}
            error={status.error}
            empty={!status.isPending && !(status.data ?? []).some((item) => item.count > 0)}
          />
        </Card>
      </ChartGrid>
      <Card className="mt-4!" title="Top SKU">
        <AppTable<TopSku>
          fillHeight={false}
          rowKey="sku_id"
          columns={skuColumns}
          dataSource={topSkus.data ?? []}
          loading={topSkus.isPending}
          pagination={false}
        />
      </Card>
      <Card className="mt-4!" title="Top 客户">
        <AppTable<TopCustomer>
          fillHeight={false}
          rowKey="customer_id"
          columns={customerColumns}
          dataSource={topCustomers.data ?? []}
          loading={topCustomers.isPending}
          pagination={false}
        />
      </Card>
      <Card className="mt-4!" title="按日汇总">
        <AppTable<SalesTrendPoint>
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
