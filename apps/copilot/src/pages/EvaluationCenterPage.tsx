import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Empty, Form, Input, Modal, Progress, Select, Space, Table, Tabs, Tag, Tree, Typography } from 'antd';
import { useState } from 'react';
import {
  createEvaluationDataset,
  createEvaluationCase,
  createEvaluationRun,
  createEvaluationComparison,
  freezeEvaluationDataset,
  getAgentTrace,
  getEvaluationRun,
  getEvaluationDataset,
  importV8EvaluationCases,
  importV9EvaluationCases,
  listEvaluationDatasets,
  listEvaluationRuns,
  listEvaluationVersions,
  type EvaluationDataset,
  type EvaluationRun,
  type EvaluationRunDetail,
} from '@/api/evaluations';
import { useCopilotStore } from '@/store';

const { Text, Title } = Typography;

function DatasetPanel() {
  const tenantId = useCopilotStore((state) => state.tenantId);
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selectedDataset, setSelectedDataset] = useState<number>();
  const [caseOpen, setCaseOpen] = useState(false);
  const [form] = Form.useForm<{ name: string; description?: string }>();
  const [caseForm] = Form.useForm<{ external_key: string; case_type: string; user_input: string; status: 'READY' | 'NEEDS_REVIEW' | 'DISABLED' }>();
  const datasets = useQuery({
    queryKey: ['tenant', tenantId, 'agent-evaluation-datasets'],
    queryFn: ({ signal }) => listEvaluationDatasets(signal),
    enabled: tenantId != null,
  });
  const create = useMutation({
    mutationFn: createEvaluationDataset,
    onSuccess: () => {
      setOpen(false);
      form.resetFields();
      void client.invalidateQueries({ queryKey: ['tenant', tenantId, 'agent-evaluation-datasets'] });
    },
  });
  const detail = useQuery({ queryKey: ['tenant', tenantId, 'agent-evaluation-dataset', selectedDataset], queryFn: ({ signal }) => getEvaluationDataset(selectedDataset!, signal), enabled: selectedDataset != null });
  const createCase = useMutation({
    mutationFn: (values: { external_key: string; case_type: string; user_input: string; status: 'READY' | 'NEEDS_REVIEW' | 'DISABLED' }) => createEvaluationCase(selectedDataset!, values),
    onSuccess: () => {
      setCaseOpen(false);
      caseForm.resetFields();
      void client.invalidateQueries({ queryKey: ['tenant', tenantId, 'agent-evaluation-dataset', selectedDataset] });
    },
  });
  const importV8 = useMutation({
    mutationFn: importV8EvaluationCases,
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tenant', tenantId, 'agent-evaluation-dataset', selectedDataset] }),
  });
  const importV9 = useMutation({
    mutationFn: importV9EvaluationCases,
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tenant', tenantId, 'agent-evaluation-dataset', selectedDataset] }),
  });
  const freeze = useMutation({
    mutationFn: freezeEvaluationDataset,
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tenant', tenantId, 'agent-evaluation-datasets'] }),
  });
  const rows = datasets.data?.items ?? [];
  return (
    <Card
      title="评测数据集"
      extra={<Button type="primary" onClick={() => setOpen(true)}>创建数据集</Button>}
    >
      {rows.length ? (
        <Table<EvaluationDataset>
          rowKey="id"
          pagination={false}
          dataSource={rows}
          columns={[
            { title: '名称', dataIndex: 'name' },
            { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
            { title: '冻结版本', dataIndex: 'current_version' },
            {
              title: '操作',
              render: (_, row) => <Space>
                <Button size="small" onClick={() => setSelectedDataset(row.id)}>查看 Case</Button>
                <Button size="small" loading={importV8.isPending} onClick={() => { setSelectedDataset(row.id); importV8.mutate(row.id); }}>导入 V8 30题</Button>
                <Button size="small" loading={importV9.isPending} onClick={() => { setSelectedDataset(row.id); importV9.mutate(row.id); }}>导入 V9 100题</Button>
                <Button size="small" loading={freeze.isPending} onClick={() => freeze.mutate(row.id)}>冻结新版本</Button>
              </Space>,
            },
          ]}
        />
      ) : <Empty description="尚无评测数据集" />}
      <Modal
        title="创建评测数据集"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.validateFields().then((values) => create.mutate(values))}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="说明"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
      <Modal width={980} title="评测 Case" open={selectedDataset != null} onCancel={() => setSelectedDataset(undefined)} footer={null}>
        <Button className="mb-3" type="primary" onClick={() => setCaseOpen(true)}>新增 Case</Button>
        <Table rowKey="id" size="small" pagination={{ pageSize: 10 }} dataSource={detail.data?.cases ?? []} columns={[
          { title: 'Key', dataIndex: 'external_key' },
          { title: '分类', dataIndex: 'case_type' },
          { title: '问题', dataIndex: 'user_input', ellipsis: true },
          { title: '审核', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
        ]} />
      </Modal>
      <Modal title="新增结构化 Case" open={caseOpen} onCancel={() => setCaseOpen(false)} onOk={() => caseForm.validateFields().then((values) => createCase.mutate(values))} confirmLoading={createCase.isPending}>
        <Form form={caseForm} layout="vertical" initialValues={{ status: 'NEEDS_REVIEW' }}>
          <Form.Item name="external_key" label="稳定 Key" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="case_type" label="分类" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="user_input" label="用户问题" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="status" label="审核状态"><Select options={['NEEDS_REVIEW', 'READY', 'DISABLED'].map((value) => ({ label: value, value }))} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

function RunPanel() {
  const tenantId = useCopilotStore((state) => state.tenantId);
  const client = useQueryClient();
  const datasets = useQuery({ queryKey: ['tenant', tenantId, 'agent-evaluation-datasets'], queryFn: ({ signal }) => listEvaluationDatasets(signal), enabled: tenantId != null });
  const runs = useQuery({ queryKey: ['tenant', tenantId, 'agent-evaluation-runs'], queryFn: ({ signal }) => listEvaluationRuns(signal), enabled: tenantId != null, refetchInterval: 3000 });
  const [datasetId, setDatasetId] = useState<number>();
  const versions = useQuery({ queryKey: ['tenant', tenantId, 'agent-evaluation-versions', datasetId], queryFn: ({ signal }) => listEvaluationVersions(datasetId!, signal), enabled: datasetId != null });
  const [versionId, setVersionId] = useState<number>();
  const [mode, setMode] = useState<'SINGLE' | 'MULTI' | 'AUTO'>('AUTO');
  const [selectedRun, setSelectedRun] = useState<number>();
  const detail = useQuery({ queryKey: ['tenant', tenantId, 'agent-evaluation-run', selectedRun], queryFn: ({ signal }) => getEvaluationRun(selectedRun!, signal), enabled: selectedRun != null });
  const create = useMutation({
    mutationFn: () => createEvaluationRun({ dataset_version_id: versionId!, mode, execution_kind: 'REPLAY', idempotency_key: crypto.randomUUID() }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['tenant', tenantId, 'agent-evaluation-runs'] }),
  });
  const rows = runs.data?.items ?? [];
  return (
    <Space direction="vertical" size={16} className="w-full">
      <Card title="启动安全评测">
        <Space wrap>
          <Select
            className="w-64"
            placeholder="选择数据集"
            options={(datasets.data?.items ?? []).filter((item) => item.current_version > 0).map((item) => ({ label: item.name, value: item.id }))}
            onChange={(value) => { setDatasetId(value); setVersionId(undefined); }}
          />
          <Select
            className="w-48"
            placeholder="选择冻结版本"
            value={versionId}
            options={(versions.data ?? []).map((item) => ({ label: `v${item.version} · ${item.ready_count}/${item.case_count} READY`, value: item.id }))}
            onChange={setVersionId}
          />
          <Select value={mode} options={['SINGLE', 'MULTI', 'AUTO'].map((value) => ({ label: value, value }))} onChange={setMode} />
          <Button type="primary" disabled={!versionId} loading={create.isPending} onClick={() => create.mutate()}>启动 Replay Run</Button>
        </Space>
        <div className="mt-3 text-xs text-slate-500">LIVE 运行需要服务端配置受控评测身份；页面不会发送用户 JWT 给 Worker。</div>
      </Card>
      <Card title="运行记录">
        {rows.length ? (
          <Table<EvaluationRun>
            rowKey="id"
            pagination={false}
            dataSource={rows}
            columns={[
              { title: 'Run', dataIndex: 'id', render: (value) => `#${value}` },
              { title: '模式', dataIndex: 'mode' },
              { title: '类型', dataIndex: 'execution_kind' },
              { title: '状态', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
              {
                title: '进度',
                render: (_, row) => <Progress percent={row.total_cases ? Math.round((row.completed_cases / row.total_cases) * 100) : 0} size="small" />,
              },
              { title: '失败', dataIndex: 'failed_cases' },
              { title: '详情', render: (_, row) => <Button size="small" onClick={() => setSelectedRun(row.id)}>Case 与指标</Button> },
            ]}
          />
        ) : <Empty description="尚无评测运行；不会显示虚构指标" />}
      </Card>
      <Modal width={960} title={`评测 Run #${selectedRun ?? ''}`} open={selectedRun != null} onCancel={() => setSelectedRun(undefined)} footer={null}>
        {detail.data ? <RunDetail detail={detail.data} /> : <div>加载中…</div>}
      </Modal>
    </Space>
  );
}

function RunDetail({ detail }: { detail: EvaluationRunDetail }) {
  const metrics = detail.metrics ?? {};
  return (
    <Space direction="vertical" className="w-full">
      <Descriptions size="small" bordered column={3} items={[
        { key: 'status', label: '状态', children: detail.status },
        { key: 'mode', label: '模式', children: detail.mode },
        { key: 'progress', label: '进度', children: `${detail.completed_cases}/${detail.total_cases}` },
      ]} />
      {Object.keys(metrics).length ? <pre className="max-h-48 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(metrics, null, 2)}</pre> : <Empty description="尚无聚合指标" />}
      <Table
        rowKey="id"
        size="small"
        pagination={{ pageSize: 10 }}
        dataSource={detail.cases}
        columns={[
          { title: 'Case', dataIndex: 'case_key' },
          { title: '执行', dataIndex: 'status', render: (value) => <Tag>{value}</Tag> },
          { title: '任务结果', dataIndex: 'task_outcome' },
          { title: '错误码', dataIndex: 'error_code', render: (value) => value ?? '-' },
        ]}
        expandable={{ expandedRowRender: (row) => <pre className="overflow-auto text-xs">{JSON.stringify({ answer: row.actual_answer, metrics: row.metrics, assertions: row.assertion_results }, null, 2)}</pre> }}
      />
    </Space>
  );
}

function ComparisonPanel() {
  const tenantId = useCopilotStore((state) => state.tenantId);
  const runs = useQuery({ queryKey: ['tenant', tenantId, 'agent-evaluation-runs'], queryFn: ({ signal }) => listEvaluationRuns(signal), enabled: tenantId != null });
  const [baseline, setBaseline] = useState<number>();
  const [candidate, setCandidate] = useState<number>();
  const compare = useMutation({ mutationFn: () => createEvaluationComparison(baseline!, candidate!) });
  const options = (runs.data?.items ?? []).map((run) => ({ label: `#${run.id} ${run.mode} ${run.status}`, value: run.id }));
  const result = compare.data as { comparable?: boolean; incomparable_reason?: string; report?: Record<string, unknown> } | undefined;
  return <Card title="Baseline / Candidate 回归对比">
    <Space wrap>
      <Select className="w-56" placeholder="Baseline Run" options={options} onChange={setBaseline} />
      <Select className="w-56" placeholder="Candidate Run" options={options} onChange={setCandidate} />
      <Button type="primary" disabled={!baseline || !candidate || baseline === candidate} loading={compare.isPending} onClick={() => compare.mutate()}>生成配对报告</Button>
    </Space>
    {result ? <div className="mt-4">
      {result.comparable ? <Alert type="success" showIcon message="冻结版本与环境严格可比" /> : <Alert type="warning" showIcon message="非严格可比" description={result.incomparable_reason} />}
      <pre className="mt-3 max-h-[480px] overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(result.report, null, 2)}</pre>
    </div> : <Empty className="mt-8" description="选择两个已完成 Run 查看真实差异" />}
  </Card>;
}

function TracePanel() {
  const tenantId = useCopilotStore((state) => state.tenantId);
  const [input, setInput] = useState('');
  const [runId, setRunId] = useState<number>();
  const trace = useQuery({ queryKey: ['tenant', tenantId, 'agent-trace', runId], queryFn: ({ signal }) => getAgentTrace(runId!, signal), enabled: runId != null });
  const data = trace.data as { agent_run?: Record<string, unknown>; tasks?: Array<Record<string, unknown>>; model_calls?: Array<Record<string, unknown>>; tool_runs?: Array<Record<string, unknown>>; evidences?: Array<Record<string, unknown>> } | undefined;
  const tree = data ? [{ title: `AgentRun #${String(data.agent_run?.id ?? '')}`, key: 'run', children: (data.tasks ?? []).map((task, index) => ({ title: `${String(task.agent_name)} · ${String(task.status)}`, key: `task-${index}`, children: [
    ...(data.model_calls ?? []).filter((item) => item.agent_task_id === task.task_id).map((item, callIndex) => ({ title: `ModelCall ${String(item.status)} · ${String(item.duration_ms ?? '-')} ms`, key: `model-${index}-${callIndex}` })),
    ...(data.tool_runs ?? []).filter((item) => item.agent_task_id === task.task_id).map((item, toolIndex) => ({ title: `Tool ${String(item.tool_name)} · ${String(item.status)}`, key: `tool-${index}-${toolIndex}` })),
    ...(data.evidences ?? []).filter((item) => item.agent_task_id === task.task_id).map((item, evidenceIndex) => ({ title: `Evidence ${String(item.citation_id)} · ${String(item.source_type)}`, key: `evidence-${index}-${evidenceIndex}` })),
  ] })) }] : [];
  return <Card title="Agent Trace Viewer">
    <Space><Input value={input} onChange={(event) => setInput(event.target.value)} placeholder="AgentRun ID" /><Button type="primary" onClick={() => setRunId(Number(input))} disabled={!Number(input)}>加载 Trace</Button></Space>
    {tree.length ? <Tree className="mt-4" defaultExpandAll treeData={tree} /> : <Empty className="mt-8" description="输入可访问的 AgentRun ID" />}
  </Card>;
}

export default function EvaluationCenterPage() {
  return (
    <div className="copilot-scroll h-full overflow-y-auto p-4 md:p-6">
      <div className="mx-auto max-w-7xl">
        <Title level={3}>Agent Evaluation Center</Title>
        <Text type="secondary">冻结数据集、异步 Run、真实 Trace、确定性指标与 Single/Multi 对照</Text>
        <Tabs className="mt-4" items={[
          { key: 'datasets', label: '数据集', children: <DatasetPanel /> },
          { key: 'runs', label: '运行与指标', children: <RunPanel /> },
          { key: 'comparison', label: 'Single / Multi 对比', children: <ComparisonPanel /> },
          { key: 'trace', label: 'Trace', children: <TracePanel /> },
        ]} />
      </div>
    </div>
  );
}
