import {
  ANALYTICS_STALE_TIME_MS,
  afterSaleTypeLabel,
  analyticsQueryKey,
  formatAnalyticsAmount,
  formatAnalyticsRate,
  toChartNumber,
  type AfterSaleTrendPoint,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Card } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo, useState } from 'react';
import { fetchAfterSaleSummary, fetchAfterSaleTrend, fetchAfterSaleTypes } from '@/api/analytics';
import { AnalyticsChart } from '@/components/analytics/AnalyticsChart';
import { AnalyticsToolbar } from '@/components/analytics/AnalyticsToolbar';
import { ChartGrid, KpiCard, KpiGrid } from '@/components/analytics/KpiCard';
import { AppTable } from '@/components/AppTable';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { defaultAnalyticsRange, rangeToAnalyticsParams } from '@/lib/analytics-range';
import { statusPieOption } from '@/components/analytics/chart-options';
import type { PageProps } from '@/router/types';

export function AfterSaleAnalyticsPage(props: PageProps) {
  const { tenantId } = usePermissions();
  const queryClient = useQueryClient();
  const [range, setRange] = useState(defaultAnalyticsRange);
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const params = { ...rangeToAnalyticsParams(range), warehouseId };
  const enabled = tenantId != null;

  const summary = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'after-sale-summary', params),
    queryFn: ({ signal }) => fetchAfterSaleSummary(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const trend = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'after-sale-trend', params),
    queryFn: ({ signal }) => fetchAfterSaleTrend(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const types = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'after-sale-types', params),
    queryFn: ({ signal }) => fetchAfterSaleTypes(params, signal),
    enabled,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });

  const trendOption = useMemo(() => {
    const points = trend.data ?? [];
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['售后单', '退货数量', '退款金额'] },
      grid: { left: 48, right: 24, top: 32, bottom: 32 },
      xAxis: { type: 'category', data: points.map((item) => item.date) },
      yAxis: [
        { type: 'value', name: '数量' },
        { type: 'value', name: '金额' },
      ],
      series: [
        { name: '售后单', type: 'bar', data: points.map((item) => item.after_sale_count) },
        { name: '退货数量', type: 'bar', data: points.map((item) => item.return_quantity) },
        {
          name: '退款金额',
          type: 'line',
          yAxisIndex: 1,
          data: points.map((item) => toChartNumber(item.refund_amount)),
        },
      ],
    };
  }, [trend.data]);

  const dayColumns: ColumnsType<AfterSaleTrendPoint> = [
    { title: '日期', dataIndex: 'date', width: 120 },
    { title: '售后单', dataIndex: 'after_sale_count', width: 90, align: 'right' },
    { title: '退货数量', dataIndex: 'return_quantity', width: 90, align: 'right' },
    {
      title: '退款金额',
      dataIndex: 'refund_amount',
      width: 120,
      align: 'right',
      render: (value: number) => formatAnalyticsAmount(value),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '售后分析'}
        description={props.description ?? '售后率按发生有效售后的销售订单去重数 ÷ 有效销售订单数。原因当前为自由文本，不做文本 Top N。'}
      />
      <AnalyticsToolbar
        range={range}
        onRangeChange={setRange}
        warehouseId={warehouseId}
        onWarehouseChange={setWarehouseId}
        onRefresh={() => {
          void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'analytics'] });
        }}
      />
      <KpiGrid>
        <KpiCard title="有效售后单" value={summary.data?.after_sale_count ?? 0} loading={summary.isPending} />
        <KpiCard title="仅退款" value={summary.data?.refund_only_count ?? 0} loading={summary.isPending} />
        <KpiCard title="仅退货" value={summary.data?.return_only_count ?? 0} loading={summary.isPending} />
        <KpiCard title="退货退款" value={summary.data?.return_and_refund_count ?? 0} loading={summary.isPending} />
        <KpiCard title="成功退款" value={formatAnalyticsAmount(summary.data?.refund_amount)} loading={summary.isPending} />
        <KpiCard title="售后率" value={formatAnalyticsRate(summary.data?.after_sale_rate)} loading={summary.isPending} hint="去重订单 / 有效订单" />
      </KpiGrid>
      <ChartGrid>
        <Card className="mt-4!" title="售后趋势">
          <AnalyticsChart
            option={trendOption}
            loading={trend.isPending}
            error={trend.error}
            empty={!trend.isPending && (trend.data?.every((item) => item.after_sale_count === 0) ?? true)}
          />
        </Card>
        <Card className="mt-4!" title="售后类型">
          <AnalyticsChart
            option={statusPieOption(
              (types.data ?? []).map((item) => ({ status: item.type, count: item.count })),
              afterSaleTypeLabel,
            )}
            loading={types.isPending}
            error={types.error}
            empty={!types.isPending && !(types.data ?? []).some((item) => item.count > 0)}
          />
        </Card>
      </ChartGrid>
      <Card className="mt-4!" title="按日汇总">
        <AppTable<AfterSaleTrendPoint>
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
