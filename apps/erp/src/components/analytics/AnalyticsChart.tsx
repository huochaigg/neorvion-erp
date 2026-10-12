import { Alert, Empty, Spin } from 'antd';
import { BarChart, LineChart, PieChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';
import { useEffect, useRef } from 'react';

echarts.use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

interface AnalyticsChartProps {
  option: EChartsCoreOption | null;
  loading?: boolean;
  error?: unknown;
  empty?: boolean;
  height?: number;
}

export function AnalyticsChart({
  option,
  loading = false,
  error,
  empty = false,
  height = 280,
}: AnalyticsChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) {
      return;
    }
    const chart = echarts.init(el);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => {
      chart.resize();
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !option || loading || error || empty) {
      return;
    }
    chartRef.current.setOption(option, true);
    chartRef.current.resize();
  }, [option, loading, error, empty]);

  return (
    <div className="relative w-full" style={{ height }}>
      <div ref={containerRef} className="h-full w-full" />
      {loading ? (
        <div className="absolute inset-0 flex items-center justify-center bg-white/70">
          <Spin />
        </div>
      ) : null}
      {error ? (
        <div className="absolute inset-0 flex items-center justify-center p-4">
          <Alert
            type="error"
            showIcon
            title="统计加载失败"
            description={error instanceof Error ? error.message : '请稍后重试'}
          />
        </div>
      ) : null}
      {!loading && !error && empty ? (
        <div className="absolute inset-0 flex items-center justify-center">
          <Empty description="暂无数据" />
        </div>
      ) : null}
    </div>
  );
}
