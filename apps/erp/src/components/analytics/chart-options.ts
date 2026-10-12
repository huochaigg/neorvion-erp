import { toChartNumber, type SalesTrendPoint } from '@neorvion/shared';

export function salesTrendOption(points: SalesTrendPoint[]) {
  return {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['销售额', '退款', '订单数'] },
    grid: { left: 48, right: 24, top: 32, bottom: 32 },
    xAxis: { type: 'category' as const, data: points.map((item) => item.date) },
    yAxis: [
      { type: 'value' as const, name: '金额' },
      { type: 'value' as const, name: '单数' },
    ],
    series: [
      { name: '销售额', type: 'line' as const, data: points.map((item) => toChartNumber(item.sales_amount)) },
      { name: '退款', type: 'bar' as const, data: points.map((item) => toChartNumber(item.refund_amount)) },
      { name: '订单数', type: 'line' as const, yAxisIndex: 1, data: points.map((item) => item.order_count) },
    ],
  };
}

export function statusPieOption(
  items: { status: string; count: number }[],
  labelOf: (status: string) => string,
) {
  const data = items
    .filter((item) => item.count > 0)
    .map((item) => ({ name: labelOf(item.status), value: item.count }));
  return {
    tooltip: { trigger: 'item' as const },
    legend: { type: 'scroll' as const, bottom: 0 },
    series: [{ type: 'pie' as const, radius: ['40%', '65%'], data }],
  };
}
