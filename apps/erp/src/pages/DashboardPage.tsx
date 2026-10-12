import {
  ANALYTICS_STALE_TIME_MS,
  analyticsQueryKey,
  formatAnalyticsAmount,
  formatAnalyticsRate,
  healthQueryKey,
  PERMISSION_CODE,
  toChartNumber,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Card, Col, Input, Row, Spin, Tag } from 'antd';
import { useMemo, useState } from 'react';
import {
  fetchAnalyticsOverview,
  fetchInventoryByWarehouse,
  fetchPurchaseTrend,
  fetchSalesTopSkus,
  fetchSalesTrend,
} from '@/api/analytics';
import { fetchHealth } from '@/api/health';
import { AnalyticsChart } from '@/components/analytics/AnalyticsChart';
import { AnalyticsToolbar } from '@/components/analytics/AnalyticsToolbar';
import { salesTrendOption } from '@/components/analytics/chart-options';
import { ChartGrid, KpiCard, KpiGrid } from '@/components/analytics/KpiCard';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { StatusTag } from '@/components/StatusTag';
import { usePermissions } from '@/hooks/usePermissions';
import { defaultAnalyticsRange, rangeToAnalyticsParams } from '@/lib/analytics-range';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function DashboardPage(props: PageProps) {
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const { hasPermission } = usePermissions();
  const queryClient = useQueryClient();
  const [aliveProbe, setAliveProbe] = useState('');
  const [range, setRange] = useState(defaultAnalyticsRange);
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const params = { ...rangeToAnalyticsParams(range), warehouseId };
  const canOverview = hasPermission(PERMISSION_CODE.analyticsOverviewRead);
  const canSales = hasPermission(PERMISSION_CODE.analyticsSalesRead);
  const canPurchase = hasPermission(PERMISSION_CODE.analyticsPurchaseRead);
  const canInventory = hasPermission(PERMISSION_CODE.analyticsInventoryRead);

  const health = useQuery({
    queryKey: healthQueryKey(tenantId),
    queryFn: ({ signal }) => fetchHealth(signal),
    retry: false,
  });
  const overview = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'overview', params),
    queryFn: ({ signal }) => fetchAnalyticsOverview(params, signal),
    enabled: tenantId != null && canOverview,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const salesTrend = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'sales-trend', params),
    queryFn: ({ signal }) => fetchSalesTrend(params, signal),
    enabled: tenantId != null && canSales,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const purchaseTrend = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'purchase-trend', params),
    queryFn: ({ signal }) => fetchPurchaseTrend(params, signal),
    enabled: tenantId != null && canPurchase,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const warehouseDist = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'inventory-by-warehouse', params),
    queryFn: ({ signal }) => fetchInventoryByWarehouse(params, signal),
    enabled: tenantId != null && canInventory,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });
  const topSkus = useQuery({
    queryKey: analyticsQueryKey(tenantId, 'sales-top-skus', params),
    queryFn: ({ signal }) => fetchSalesTopSkus({ ...params, limit: 10 }, signal),
    enabled: tenantId != null && canSales,
    staleTime: ANALYTICS_STALE_TIME_MS,
  });

  const purchaseOption = useMemo(() => {
    const points = purchaseTrend.data ?? [];
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['采购额', '采购单数'] },
      grid: { left: 48, right: 24, top: 32, bottom: 32 },
      xAxis: { type: 'category' as const, data: points.map((item) => item.date) },
      yAxis: [
        { type: 'value' as const, name: '金额' },
        { type: 'value' as const, name: '单数' },
      ],
      series: [
        { name: '采购额', type: 'line' as const, data: points.map((item) => toChartNumber(item.purchase_amount)) },
        { name: '采购单数', type: 'bar' as const, yAxisIndex: 1, data: points.map((item) => item.purchase_order_count) },
      ],
    };
  }, [purchaseTrend.data]);
  const warehouseOption = useMemo(() => {
    const rows = warehouseDist.data ?? [];
    return {
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['可用库存'] },
      grid: { left: 48, right: 16, top: 32, bottom: 48 },
      xAxis: {
        type: 'category' as const,
        data: rows.map((item) => item.warehouse_name),
        axisLabel: { rotate: 20 },
      },
      yAxis: { type: 'value' as const },
      series: [{ name: '可用库存', type: 'bar' as const, data: rows.map((item) => item.available_quantity) }],
    };
  }, [warehouseDist.data]);

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '经营总览'}
        description={props.description ?? '基于现有业务单据的实时聚合。有效销售排除草稿与取消，净销售只扣成功退款。'}
        extra={<StatusTag tone="ready">V13 数据看板</StatusTag>}
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
      <Can permission={PERMISSION_CODE.analyticsOverviewRead}>
        <KpiGrid>
          <KpiCard title="销售额" value={formatAnalyticsAmount(overview.data?.sales.gross_sales_amount)} loading={overview.isPending} to="/analytics/sales" />
          <KpiCard title="净销售额" value={formatAnalyticsAmount(overview.data?.sales.net_sales_amount)} loading={overview.isPending} />
          <KpiCard title="有效订单" value={overview.data?.sales.order_count ?? 0} loading={overview.isPending} to="/orders/list" />
          <KpiCard title="采购额" value={formatAnalyticsAmount(overview.data?.purchases.purchase_amount)} loading={overview.isPending} to="/analytics/purchases" />
          <KpiCard title="可用库存" value={overview.data?.inventory.total_available_quantity ?? 0} loading={overview.isPending} to="/analytics/inventory" />
          <KpiCard title="售后率" value={formatAnalyticsRate(overview.data?.after_sales.after_sale_rate)} loading={overview.isPending} to="/analytics/after-sales" />
        </KpiGrid>
        {overview.isError ? (
          <Alert className="mt-3" type="error" showIcon title="经营总览加载失败" description={overview.error instanceof Error ? overview.error.message : '请稍后重试'} />
        ) : null}
      </Can>
      <ChartGrid>
        <Can permission={PERMISSION_CODE.analyticsSalesRead}>
          <Card className="mt-4!" title="销售趋势">
            <AnalyticsChart
              option={salesTrendOption(salesTrend.data ?? [])}
              loading={salesTrend.isPending}
              error={salesTrend.error}
              empty={!salesTrend.isPending && (salesTrend.data?.every((item) => item.order_count === 0) ?? true)}
            />
          </Card>
        </Can>
        <Can permission={PERMISSION_CODE.analyticsPurchaseRead}>
          <Card className="mt-4!" title="采购趋势">
            <AnalyticsChart
              option={purchaseOption}
              loading={purchaseTrend.isPending}
              error={purchaseTrend.error}
              empty={!purchaseTrend.isPending && (purchaseTrend.data?.every((item) => item.purchase_order_count === 0) ?? true)}
            />
          </Card>
        </Can>
        <Can permission={PERMISSION_CODE.analyticsInventoryRead}>
          <Card className="mt-4" title="仓库可用库存">
            <AnalyticsChart
              option={warehouseOption}
              loading={warehouseDist.isPending}
              error={warehouseDist.error}
              empty={!warehouseDist.isPending && !(warehouseDist.data ?? []).some((item) => item.available_quantity > 0)}
            />
          </Card>
        </Can>
        <Can permission={PERMISSION_CODE.analyticsSalesRead}>
          <Card className="mt-4" title="Top SKU">
            <AppTable
              fillHeight={false}
              rowKey="sku_id"
              pagination={false}
              loading={topSkus.isPending}
              dataSource={topSkus.data ?? []}
              columns={[
                { title: 'SKU', dataIndex: 'sku_code', width: 140, render: (value: string) => <CodeCell value={value} /> },
                { title: '商品', dataIndex: 'product_name', render: (value: string) => <EllipsisCell value={value} /> },
                { title: '销量', dataIndex: 'sales_quantity', width: 80, align: 'right' },
                {
                  title: '销售额',
                  dataIndex: 'sales_amount',
                  width: 120,
                  align: 'right',
                  render: (value: number) => formatAnalyticsAmount(value),
                },
              ]}
            />
          </Card>
        </Can>
      </ChartGrid>
      <Can permission={PERMISSION_CODE.analyticsOverviewRead}>
        <Card className="mt-4!" title="待处理事项">
          <KpiGrid>
            <KpiCard title="待确认销售" value={overview.data?.pending.pending_confirmation_order_count ?? 0} to="/orders/list" />
            <KpiCard title="待出库" value={overview.data?.pending.waiting_outbound_order_count ?? 0} to="/orders/list" />
            <KpiCard title="待收货采购" value={overview.data?.pending.pending_receipt_order_count ?? 0} to="/purchases/list" />
            <KpiCard title="待审核售后" value={overview.data?.pending.pending_after_sale_count ?? 0} to="/after-sales/list" />
            <KpiCard title="待退款售后" value={overview.data?.pending.waiting_refund_after_sale_count ?? 0} to="/refunds" />
            <KpiCard title="待处理采购退货" value={overview.data?.pending.pending_purchase_return_count ?? 0} to="/purchase-returns" />
            <KpiCard title="低库存" value={overview.data?.pending.low_stock_sku_count ?? 0} to="/inventory/list" />
          </KpiGrid>
        </Card>
      </Can>
      <Row className="mt-4" gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="运行上下文">
            <p className="mb-2 text-sm text-slate-600">
              嵌入模式：{window.__POWERED_BY_WUJIE__ ? '无界子应用' : '独立启动'}
            </p>
            <p className="mb-0 text-sm text-slate-600">当前租户：{tenantId ?? '未选择'}</p>
            <Input
              className="mt-3!"
              value={aliveProbe}
              onChange={(event) => setAliveProbe(event.target.value)}
              placeholder="保活探测：输入后离开再回来应仍在；切租户后应清空"
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="API 连通性">
            {health.isLoading ? <Spin /> : null}
            {health.isError ? (
              <Alert
                type="warning"
                showIcon
                title="无法连接后端"
                description={health.error instanceof Error ? health.error.message : '请启动 FastAPI 8011 端口'}
              />
            ) : null}
            {health.data ? (
              <div className="flex flex-wrap gap-2">
                <Tag color={health.data.mysql === 'ok' ? 'success' : 'error'}>MySQL {health.data.mysql}</Tag>
                <Tag color={health.data.redis === 'ok' ? 'success' : 'error'}>Redis {health.data.redis}</Tag>
                <Tag>{health.data.milestone}</Tag>
              </div>
            ) : null}
          </Card>
        </Col>
      </Row>
    </FormPageContainer>
  );
}
