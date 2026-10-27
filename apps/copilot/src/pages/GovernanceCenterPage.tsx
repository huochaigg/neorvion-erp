import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Space, Switch, Table, Tabs, Tag, Typography } from 'antd';
import {
  getAIOperations,
  getAIUsage,
  getGovernancePolicy,
  getTenantQuota,
  listGovernanceAudits,
  listModels,
  listProviders,
  previewRetention,
  probeProvider,
  updateGovernancePolicy,
  type GovernancePolicy,
} from '@/api/governance';
import { useCopilotStore } from '@/store';

const { Text, Title } = Typography;

export default function GovernanceCenterPage({ canManage }: { canManage: boolean }) {
  const tenantId = useCopilotStore((s) => s.tenantId);
  const query = useQueryClient();
  const providers = useQuery({ queryKey: ['tenant', tenantId, 'ai-providers'], queryFn: ({ signal }) => listProviders(signal) });
  const models = useQuery({ queryKey: ['tenant', tenantId, 'ai-models'], queryFn: ({ signal }) => listModels(signal) });
  const policy = useQuery({ queryKey: ['tenant', tenantId, 'ai-policy'], queryFn: ({ signal }) => getGovernancePolicy(signal) });
  const quota = useQuery({ queryKey: ['tenant', tenantId, 'ai-quota'], queryFn: ({ signal }) => getTenantQuota(signal) });
  const usage = useQuery({ queryKey: ['tenant', tenantId, 'ai-usage'], queryFn: ({ signal }) => getAIUsage(signal) });
  const operations = useQuery({ queryKey: ['tenant', tenantId, 'ai-operations'], queryFn: ({ signal }) => getAIOperations(signal), refetchInterval: 30_000 });
  const audits = useQuery({ queryKey: ['tenant', tenantId, 'ai-audits'], queryFn: ({ signal }) => listGovernanceAudits(signal) });
  const probe = useMutation({ mutationFn: probeProvider, onSuccess: () => void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'ai-providers'] }) });
  const savePolicy = useMutation({
    mutationFn: (value: Omit<GovernancePolicy, 'id'>) => updateGovernancePolicy(value),
    onSuccess: () => void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'ai-policy'] }),
  });
  const retention = useMutation({ mutationFn: previewRetention });

  const policyToggle = (key: 'multi_agent_enabled' | 'insight_analysis_enabled' | 'live_evaluation_enabled', checked: boolean) => {
    if (!policy.data) return;
    savePolicy.mutate({
      allowed_provider_codes: policy.data.allowed_provider_codes,
      allowed_model_names: policy.data.allowed_model_names,
      allowed_agents: policy.data.allowed_agents,
      allowed_tools: policy.data.allowed_tools,
      multi_agent_enabled: policy.data.multi_agent_enabled,
      insight_analysis_enabled: policy.data.insight_analysis_enabled,
      live_evaluation_enabled: policy.data.live_evaluation_enabled,
      max_context_tokens: policy.data.max_context_tokens,
      trace_retention_days: policy.data.trace_retention_days,
      conversation_retention_days: policy.data.conversation_retention_days,
      [key]: checked,
    });
  };
  const operationItems = Object.entries(operations.data ?? {}).map(([key, value]) => ({ key, value }));

  return (
    <Tabs items={[
      { key: 'operations', label: '运行态势', children: <Space direction="vertical" className="w-full" size="middle">
        <Alert type="info" showIcon message="30 秒自动刷新；这里只展示安全聚合指标，不展示 Prompt、密钥或思维过程。" />
        <div className="grid gap-3 md:grid-cols-3">{operationItems.map((item) => <Card key={item.key}><Text type="secondary">{item.key}</Text><Title level={3}>{item.value}</Title></Card>)}</div>
      </Space> },
      { key: 'models', label: '模型与 Provider', children: <Space direction="vertical" className="w-full" size="middle">
        <Table rowKey="id" loading={providers.isPending} dataSource={providers.data ?? []} pagination={false} columns={[
          { title: 'Provider', dataIndex: 'display_name' },
          { title: '地址', dataIndex: 'base_url' },
          { title: '密钥', render: (_, row) => <Tag color={row.secret_configured ? 'green' : 'orange'}>{row.secret_env_name} · {row.secret_configured ? '已配置' : '未配置'}</Tag> },
          { title: '探测', render: (_, row) => <Space><Tag>{row.last_probe_status}</Tag>{canManage && <Button size="small" loading={probe.isPending} onClick={() => probe.mutate(row.id)}>探测</Button>}</Space> },
          { title: '状态', dataIndex: 'status' },
        ]} />
        <Table rowKey="id" loading={models.isPending} dataSource={models.data ?? []} pagination={false} columns={[
          { title: '模型', dataIndex: 'model_name' }, { title: '用途', render: (_, row) => row.purposes.map((x) => <Tag key={x}>{x}</Tag>) },
          { title: '上下文', dataIndex: 'context_window' }, { title: '工具调用', render: (_, row) => row.supports_tools ? '支持' : '不支持' },
        ]} />
      </Space> },
      { key: 'budget', label: '用量与预算', children: <Space direction="vertical" className="w-full">
        <Descriptions bordered column={2} items={quota.data ? Object.entries(quota.data).filter(([key]) => key !== 'id').map(([key, value]) => ({ key, label: key, children: String(value ?? '未知') })) : []} />
        <Card title="本月真实 ModelCall 汇总"><pre className="overflow-auto text-xs">{JSON.stringify(usage.data ?? {}, null, 2)}</pre></Card>
        <Text type="secondary">Provider 未返回 Token 或未配置价格时明确显示未知，不按字符数伪造账单。</Text>
      </Space> },
      { key: 'policy', label: '策略与安全', children: <Space direction="vertical" className="w-full">
        {(['multi_agent_enabled', 'insight_analysis_enabled', 'live_evaluation_enabled'] as const).map((key) => <Card key={key} size="small"><Space><Switch disabled={!canManage} checked={Boolean(policy.data?.[key])} loading={savePolicy.isPending} onChange={(value) => policyToggle(key, value)} /><Text>{key}</Text></Space></Card>)}
        <Alert type="warning" showIcon message="LIVE 评测与洞察分析默认关闭；启用策略仍不会绕过服务身份、配额和只读工具边界。" />
      </Space> },
      { key: 'audit', label: '审计与数据', children: <Space direction="vertical" className="w-full">
        <Button disabled={!canManage} loading={retention.isPending} onClick={() => retention.mutate()}>运行保留策略 Dry Run</Button>
        {retention.data && <Card><pre className="overflow-auto text-xs">{JSON.stringify(retention.data, null, 2)}</pre></Card>}
        <Table rowKey={(row) => String(row.id)} loading={audits.isPending} dataSource={audits.data ?? []} columns={[
          { title: '时间', dataIndex: 'created_at' }, { title: '操作', dataIndex: 'action' }, { title: '对象', dataIndex: 'target_type' }, { title: '结果', dataIndex: 'outcome' },
        ]} />
      </Space> },
    ]} />
  );
}
