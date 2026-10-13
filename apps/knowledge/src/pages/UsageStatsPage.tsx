import { knowledgeRetrievalStrategyLabel, knowledgeUsageStatsQueryKey } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Card, Select, Statistic } from 'antd';
import { useEffect, useState } from 'react';
import { fetchUsageStats } from '@/api/evaluation';
import { MetricBars } from '@/components/MetricBars';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';

export function UsageStatsPage() {
  const { tenantId } = usePermissions();
  const [days, setDays] = useState(7);

  useEffect(() => {
    setDays(7);
  }, [tenantId]);

  const query = useQuery({
    queryKey: knowledgeUsageStatsQueryKey(tenantId, days),
    queryFn: ({ signal }) => fetchUsageStats(days, signal),
    enabled: tenantId != null,
  });

  const data = query.data;
  const strategyItems = Object.entries(data?.strategy_counts ?? {}).map(([key, value]) => ({
    label: knowledgeRetrievalStrategyLabel(key),
    value: data && data.query_count > 0 ? value / data.query_count : 0,
  }));

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader
        title="使用统计"
        description="来自当前租户的 retrieval_logs 与问答消息，不是硬编码假数据。"
        extra={
          <Select
            value={days}
            onChange={setDays}
            options={[
              { value: 1, label: '近 1 天' },
              { value: 7, label: '近 7 天' },
              { value: 30, label: '近 30 天' },
            ]}
          />
        }
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card size="small">
          <Statistic title="查询次数" value={data?.query_count ?? 0} loading={query.isLoading} />
        </Card>
        <Card size="small">
          <Statistic title="检索有结果" value={data?.search_success ?? 0} loading={query.isLoading} />
        </Card>
        <Card size="small">
          <Statistic title="空召回" value={data?.search_empty ?? 0} loading={query.isLoading} />
        </Card>
        <Card size="small">
          <Statistic
            title="估算费用 USD"
            value={data?.estimated_cost_usd ?? '-'}
            loading={query.isLoading}
          />
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card size="small" title="延迟">
          <Statistic title="P50" value={data?.latency_p50_ms ?? '-'} suffix="ms" />
          <Statistic className="mt-3" title="P95" value={data?.latency_p95_ms ?? '-'} suffix="ms" />
        </Card>
        <Card size="small" title="Token">
          <Statistic title="Prompt" value={data?.prompt_tokens ?? 0} />
          <Statistic className="mt-3" title="Completion" value={data?.completion_tokens ?? 0} />
        </Card>
        <Card size="small" title="检索策略占比" className="lg:col-span-2">
          {strategyItems.length ? <MetricBars items={strategyItems} /> : <div className="text-sm text-slate-500">暂无检索日志</div>}
        </Card>
      </div>
      {data?.note ? <p className="mt-3 text-xs text-slate-500">{data.note}</p> : null}
    </div>
  );
}
