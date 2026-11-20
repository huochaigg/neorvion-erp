import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Button, Card, Descriptions, Drawer, Empty, Form, Input, InputNumber, message,
  Modal, Select, Space, Table, Tabs, Tag, Typography, Upload,
} from 'antd';
import { useMemo, useState } from 'react';
import {
  createMcpServer, createSkill, createSkillVersion, diffSkillVersions, discoverMcpTools, getSkill, importSkillPackage, importSkillTemplates,
  listMcpServers, listMcpTools, listSkillRuns, listSkills, probeMcpServer, reviewMcpServer,
  reviewMcpTool, reviewSkill, rollbackSkill, runSkill, setMcpServerEnabled, setSkillDeprecated, setSkillEnabled,
  type JsonSchema, type SkillRun, type SkillVersionDiff,
} from '@/api/ecosystem';

const { Paragraph, Text, Title } = Typography;

interface Props {
  canMcpRead: boolean;
  canMcpManage: boolean;
  canSkillRead: boolean;
  canSkillManage: boolean;
  canSkillRun: boolean;
}

const json = (value: unknown) => JSON.stringify(value, null, 2);

function errorText(error: unknown) {
  return error instanceof Error ? error.message : '请求失败，请稍后重试';
}

function inputForSchema(schema: JsonSchema) {
  if (schema.type === 'integer' || schema.type === 'number') {
    return <InputNumber className="w-full" min={schema.minimum} max={schema.maximum} />;
  }
  if (schema.type === 'boolean') {
    return <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />;
  }
  if (schema.type === 'array' || schema.type === 'object') {
    return <Input.TextArea rows={3} placeholder={schema.type === 'array' ? '[1, 2]' : '{"key":"value"}'} />;
  }
  return <Input placeholder={schema.format === 'date' ? 'YYYY-MM-DD' : schema.description} />;
}

function parseSchemaInput(schema: JsonSchema, values: Record<string, unknown>) {
  const output: Record<string, unknown> = {};
  for (const [name, value] of Object.entries(values)) {
    const field = schema.properties?.[name];
    if (value === undefined || value === '') continue;
    if (field?.type === 'array' || field?.type === 'object') {
      output[name] = JSON.parse(String(value));
    } else output[name] = value;
  }
  return output;
}

export function RunDetail({ run }: { run: SkillRun }) {
  const evidence = run.output_snapshot.evidence ?? [];
  const toolCalls = run.output_snapshot.tool_calls ?? [];
  return (
    <Space direction="vertical" className="w-full" size="middle">
      {run.safe_error && <Alert type="error" showIcon message={run.safe_error} />}
      <Descriptions size="small" bordered column={2} items={[
        { key: 'status', label: '状态', children: <Tag>{run.status}</Tag> },
        { key: 'version', label: '版本', children: `v${run.skill_version}` },
        { key: 'started', label: '开始', children: run.started_at ?? '-' },
        { key: 'finished', label: '结束', children: run.finished_at ?? '-' },
      ]} />
      <div><Text strong>结构化结果</Text><pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-100">{json(run.output_snapshot.result ?? {})}</pre></div>
      <div><Text strong>Tool 执行摘要</Text><pre className="mt-2 max-h-52 overflow-auto rounded bg-slate-100 p-3 text-xs">{json(toolCalls)}</pre></div>
      <div><Text strong>Evidence</Text><pre className="mt-2 max-h-72 overflow-auto rounded bg-slate-100 p-3 text-xs">{json(evidence)}</pre></div>
    </Space>
  );
}

export default function EcosystemManagementPage({
  canMcpRead, canMcpManage, canSkillRead, canSkillManage, canSkillRun,
}: Props) {
  const queryClient = useQueryClient();
  const [serverOpen, setServerOpen] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);
  const [selectedSkillId, setSelectedSkillId] = useState<number>();
  const [search, setSearch] = useState('');
  const [selectedRun, setSelectedRun] = useState<SkillRun>();
  const [versionDiff, setVersionDiff] = useState<SkillVersionDiff>();
  const [versionOpen, setVersionOpen] = useState(false);
  const [serverForm] = Form.useForm();
  const [skillForm] = Form.useForm();
  const [runForm] = Form.useForm();
  const [versionForm] = Form.useForm<{ version_json: string }>();
  const servers = useQuery({ queryKey: ['mcp-servers'], queryFn: ({ signal }) => listMcpServers(signal), enabled: canMcpRead });
  const tools = useQuery({ queryKey: ['mcp-tools'], queryFn: ({ signal }) => listMcpTools(signal), enabled: canMcpRead });
  const skills = useQuery({ queryKey: ['agent-skills'], queryFn: ({ signal }) => listSkills(signal), enabled: canSkillRead });
  const detail = useQuery({ queryKey: ['agent-skill', selectedSkillId], queryFn: ({ signal }) => getSkill(selectedSkillId!, signal), enabled: selectedSkillId != null });
  const runs = useQuery({ queryKey: ['agent-skill-runs', selectedSkillId], queryFn: ({ signal }) => listSkillRuns(selectedSkillId!, signal), enabled: selectedSkillId != null });
  const compareVersion = useMutation({ mutationFn: ({ from, to }: { from: number; to: number }) => diffSkillVersions(selectedSkillId!, from, to), onSuccess: setVersionDiff });
  const saveVersion = useMutation({ mutationFn: (payload: Record<string, unknown>) => createSkillVersion(selectedSkillId!, payload), onSuccess: () => { setVersionOpen(false); versionForm.resetFields(); void queryClient.invalidateQueries({ queryKey: ['agent-skill', selectedSkillId] }); } });
  const currentVersion = detail.data?.versions.find((item) => item.version === detail.data?.current_version);
  const filteredSkills = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return skills.data ?? [];
    return (skills.data ?? []).filter((item) => `${item.name} ${item.skill_key} ${item.description}`.toLowerCase().includes(keyword));
  }, [search, skills.data]);
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['mcp-servers'] }),
      queryClient.invalidateQueries({ queryKey: ['mcp-tools'] }),
      queryClient.invalidateQueries({ queryKey: ['agent-skills'] }),
      queryClient.invalidateQueries({ queryKey: ['agent-skill', selectedSkillId] }),
      queryClient.invalidateQueries({ queryKey: ['agent-skill-runs', selectedSkillId] }),
    ]);
  };
  const action = useMutation({
    mutationFn: (work: () => Promise<unknown>) => work(),
    onSuccess: refresh,
    onError: (error) => message.error(errorText(error)),
  });
  const execute = useMutation({
    mutationFn: async () => {
      if (!selectedSkillId || !currentVersion) throw new Error('请先选择 Skill');
      const values = await runForm.validateFields();
      return runSkill(selectedSkillId, {
        input: parseSchemaInput(currentVersion.input_schema, values.input ?? {}),
        agent_name: values.agent_name,
        idempotency_key: crypto.randomUUID(),
      });
    },
    onSuccess: async (result) => { setSelectedRun(result); await refresh(); },
    onError: (error) => message.error(errorText(error)),
  });
  const submitServer = async () => {
    const values = await serverForm.validateFields();
    await createMcpServer({ ...values, transport_type: 'STREAMABLE_HTTP', authentication_type: values.credential_reference ? 'BEARER_ENV' : 'NONE', allowed_tools: [], denied_tools: [], allowed_resources: {}, timeout_seconds: 10, max_retries: 1, concurrency_limit: 2 });
    setServerOpen(false); serverForm.resetFields(); await refresh();
  };
  const submitSkill = async () => {
    const values = await skillForm.validateFields();
    let version: Record<string, unknown>;
    try {
      version = JSON.parse(values.version_json);
    } catch {
      message.error('版本配置不是有效 JSON');
      return;
    }
    await createSkill({ skill_key: values.skill_key, name: values.name, description: values.description, version });
    setSkillOpen(false); skillForm.resetFields(); await refresh();
  };
  return <>
    <Alert className="mb-4" type="warning" showIcon message="外部能力默认关闭" description="MCP 与 Skill 都要经过服务端审核、IAM、租户策略、Agent 和 Tool 白名单校验。手动运行始终可用；Chat 自动选择仅在服务端 SKILL_CHAT_ENABLED 灰度开关开启时生效。" />
    <Tabs items={[
      ...(canMcpRead ? [{
        key: 'servers', label: 'MCP Servers', children: <Card extra={<Button disabled={!canMcpManage} onClick={() => setServerOpen(true)}>新增 Server</Button>}><Table rowKey="id" loading={servers.isPending} dataSource={servers.data ?? []} pagination={false} columns={[
          { title: 'Server', dataIndex: 'display_name' }, { title: 'Endpoint', dataIndex: 'endpoint', ellipsis: true },
          { title: '审核', dataIndex: 'approval_status', render: (value: string) => <Tag>{value}</Tag> },
          { title: '健康', dataIndex: 'health_status', render: (value: string) => <Tag>{value}</Tag> },
          {
            title: '操作', render: (_, row) => <Space wrap>
              <Button size="small" disabled={!canMcpManage} onClick={() => action.mutate(() => probeMcpServer(row.id))}>探测</Button>
              <Button size="small" disabled={!canMcpManage} onClick={() => action.mutate(() => discoverMcpTools(row.id))}>发现</Button>
              <Button size="small" disabled={!canMcpManage} onClick={() => action.mutate(() => reviewMcpServer(row.id, true))}>审核</Button>
              <Button size="small" disabled={!canMcpManage || row.health_status !== 'HEALTHY'} onClick={() => action.mutate(() => setMcpServerEnabled(row.id, !row.enabled))}>{row.enabled ? '停用' : '启用'}</Button>
            </Space>
          },
        ]} /></Card>
      },
      {
        key: 'tools', label: 'Tool Registry', children: <Card><Table rowKey="id" loading={tools.isPending} dataSource={tools.data ?? []} pagination={false} columns={[
          { title: '工具', dataIndex: 'qualified_name' }, { title: '风险', dataIndex: 'risk_level', render: (value: string) => <Tag color="green">{value}</Tag> },
          { title: 'Schema', dataIndex: 'schema_hash', render: (value: string) => <Text code>{value.slice(0, 12)}</Text> },
          { title: '状态', dataIndex: 'approval_status', render: (value: string) => <Tag>{value}</Tag> },
          { title: '操作', render: (_, row) => <Button size="small" disabled={!canMcpManage || row.approval_status === 'APPROVED'} onClick={() => action.mutate(() => reviewMcpTool(row.id, true))}>审核只读版本</Button> },
        ]} /></Card>
      }] : []),
      ...(canSkillRead ? [{
        key: 'skills',
        label: 'Agent Skills',
        children: (
          <Card
            className="[&_.ant-card-head-wrapper]:gap-4"
            title={
              <Input.Search
                allowClear
                className="max-w-sm"
                placeholder="搜索名称、Key 或说明"
                onSearch={setSearch}
                onChange={(event) => setSearch(event.target.value)}
              />
            }
            extra={
              <Space wrap>
                <Button
                  disabled={!canSkillManage}
                  loading={action.isPending}
                  onClick={() => action.mutate(async () => {
                    const results = await importSkillTemplates();
                    message.success(results.map((item) => `${item.skill_key}: ${item.status}`).join('；'));
                  })}
                >
                  导入内置模板
                </Button>
                <Upload
                  accept=".zip"
                  maxCount={1}
                  showUploadList={false}
                  disabled={!canSkillManage}
                  beforeUpload={(file) => {
                    action.mutate(async () => {
                      const result = await importSkillPackage(file);
                      message.success(`${result.skill_key}: ${result.status}`);
                    });
                    return Upload.LIST_IGNORE;
                  }}
                >
                  <Button disabled={!canSkillManage} loading={action.isPending}>导入 Skill 包</Button>
                </Upload>
                <Button disabled={!canSkillManage} onClick={() => setSkillOpen(true)}>新增 Skill</Button>
              </Space>
            }
          >
            <Table
              rowKey="id"
              loading={skills.isPending}
              dataSource={filteredSkills}
              pagination={{ pageSize: 10 }}
              columns={[
                { title: 'Skill', dataIndex: 'name' },
                { title: 'Key', dataIndex: 'skill_key' },
                { title: '版本', dataIndex: 'current_version' },
                {
                  title: '审核',
                  dataIndex: 'approval_status',
                  render: (value: string) => <Tag>{value}</Tag>,
                },
                {
                  title: '启用',
                  dataIndex: 'enabled',
                  render: (value: boolean) => (
                    <Tag color={value ? 'green' : 'default'}>{value ? '是' : '否'}</Tag>
                  ),
                },
                {
                  title: '操作',
                  render: (_, row) => (
                    <Space wrap>
                      <Button
                        size="small"
                        onClick={() => {
                          setSelectedSkillId(row.id);
                          setSelectedRun(undefined);
                        }}
                      >
                        详情 / 运行
                      </Button>
                      <Button
                        size="small"
                        disabled={!canSkillManage || row.approval_status === 'APPROVED'}
                        onClick={() => action.mutate(() => reviewSkill(row.id, true))}
                      >
                        审核
                      </Button>
                      <Button
                        size="small"
                        disabled={!canSkillManage || row.approval_status !== 'APPROVED'}
                        onClick={() => action.mutate(() => setSkillEnabled(row.id, !row.enabled))}
                      >
                        {row.enabled ? '停用' : '启用'}
                      </Button>
                      <Button
                        size="small"
                        danger
                        disabled={!canSkillManage}
                        onClick={() => action.mutate(() => setSkillDeprecated(row.id, row.approval_status !== 'DEPRECATED'))}
                      >
                        {row.approval_status === 'DEPRECATED' ? '撤销弃用' : '标记弃用'}
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        ),
      }] : []),
    ]} />
    <Modal title="新增 MCP Server" open={serverOpen} onCancel={() => setServerOpen(false)} onOk={submitServer}><Paragraph type="secondary">Endpoint 必须先加入部署域名白名单；这里只填写 Secret 环境变量名。</Paragraph><Form layout="vertical" form={serverForm}><Form.Item name="server_key" label="Server Key" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="display_name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="description" label="说明"><Input.TextArea /></Form.Item><Form.Item name="endpoint" label="HTTPS Endpoint" rules={[{ required: true, type: 'url' }]}><Input /></Form.Item><Form.Item name="credential_reference" label="Secret 环境变量名"><Input placeholder="MCP_VENDOR_TOKEN" /></Form.Item></Form></Modal>
    <Modal width={760} title="新增只读 Skill" open={skillOpen} onCancel={() => setSkillOpen(false)} onOk={submitSkill}><Alert className="mb-3" type="info" message="完整版本配置采用严格 JSON" description="后端仍会校验 Schema、Agent、Tool、IAM 权限和 READ_ONLY 风险等级。" /><Form layout="vertical" form={skillForm}><Form.Item name="skill_key" label="Skill Key" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="description" label="说明" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="version_json" label="版本配置 JSON" rules={[{ required: true }]}><Input.TextArea rows={14} /></Form.Item></Form></Modal>
    <Drawer width={900} title={detail.data ? `${detail.data.name} · ${detail.data.skill_key}` : 'Skill 详情'} open={selectedSkillId != null} onClose={() => setSelectedSkillId(undefined)}>
      {detail.isPending ? <Card loading /> : currentVersion ? <Tabs items={[
        {
          key: 'config', label: '版本与配置', children: <Space direction="vertical" className="w-full" size="middle"><Button disabled={!canSkillManage} onClick={() => { versionForm.setFieldValue('version_json', json({ instructions: currentVersion.instructions, input_schema: currentVersion.input_schema, output_schema: currentVersion.output_schema, allowed_agents: currentVersion.allowed_agents, required_permissions: currentVersion.required_permissions, allowed_tools: currentVersion.allowed_tools, required_evidence: currentVersion.required_evidence, risk_level: currentVersion.risk_level, timeout_seconds: currentVersion.timeout_seconds, token_budget: currentVersion.token_budget, source_format: currentVersion.source_format, source_metadata: currentVersion.source_metadata, resources: currentVersion.resources })); setVersionOpen(true); }}>基于当前配置创建新版本</Button><Descriptions bordered column={2} items={[
            { key: 'version', label: '当前版本', children: `v${currentVersion.version}` }, { key: 'approval', label: '审核', children: currentVersion.approval_status },
            { key: 'source', label: '来源格式', children: currentVersion.source_format }, { key: 'references', label: 'References', children: Object.keys(currentVersion.resources ?? {}).join(', ') || '-' },
            { key: 'agents', label: 'Agents', children: currentVersion.allowed_agents.join(', ') }, { key: 'tools', label: 'Tools', children: currentVersion.allowed_tools.join(', ') },
            { key: 'permissions', label: '权限', children: currentVersion.required_permissions.join(', ') }, { key: 'limits', label: '约束', children: `${currentVersion.timeout_seconds}s / ${currentVersion.token_budget} tokens / ${currentVersion.risk_level}` },
            { key: 'dependencies', label: 'Skill 依赖', children: Array.isArray(currentVersion.source_metadata.dependencies) ? currentVersion.source_metadata.dependencies.join(', ') || '-' : '-' },
          ]} /><div><Title level={5}>SKILL.md</Title><pre className="max-h-[32rem] overflow-auto rounded bg-slate-100 p-3 text-xs whitespace-pre-wrap">{`---\n${json(currentVersion.source_metadata ?? {})}\n---\n\n${currentVersion.instructions}`}</pre></div><div><Title level={5}>References</Title>{Object.entries(currentVersion.resources ?? {}).length ? <Tabs items={Object.entries(currentVersion.resources).map(([path, content]) => ({ key: path, label: path.split('/').at(-1), children: <pre className="max-h-80 overflow-auto rounded bg-slate-100 p-3 text-xs whitespace-pre-wrap">{content}</pre> }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无 Reference" />}</div><div><Title level={5}>Input Schema</Title><pre className="overflow-auto rounded bg-slate-100 p-3 text-xs">{json(currentVersion.input_schema)}</pre></div><div><Title level={5}>Output Schema</Title><pre className="overflow-auto rounded bg-slate-100 p-3 text-xs">{json(currentVersion.output_schema)}</pre></div><Title level={5}>版本历史</Title><Table rowKey="id" size="small" pagination={false} dataSource={detail.data?.versions ?? []} columns={[{ title: '版本', dataIndex: 'version' }, { title: '格式', dataIndex: 'source_format' }, { title: '审核', dataIndex: 'approval_status' }, { title: 'Hash', dataIndex: 'content_hash', render: (value: string) => <Text code>{value.slice(0, 16)}</Text> }, { title: '创建时间', dataIndex: 'created_at' }, { title: '操作', render: (_, row) => <Space>{row.version === currentVersion.version ? '-' : <><Button size="small" loading={compareVersion.isPending} onClick={() => compareVersion.mutate({ from: row.version, to: currentVersion.version })}>Diff</Button><Button size="small" danger disabled={!canSkillManage} onClick={() => action.mutate(() => rollbackSkill(selectedSkillId!, row.version))}>回滚到此版本</Button></>}</Space> }]} /></Space>
        },
        { key: 'run', label: '手动运行', children: canSkillRun ? <Space direction="vertical" className="w-full" size="middle"><Alert type="info" showIcon message="同步 HTTP 执行" description="页面会等待接口返回；关闭页面或 HTTP 断开不代表下游 Tool 已停止，最终状态以运行记录为准。" /><Form form={runForm} layout="vertical" initialValues={{ agent_name: currentVersion.allowed_agents[0] }}><Form.Item name="agent_name" label="专业 Agent" rules={[{ required: true }]}><Select options={currentVersion.allowed_agents.map((value) => ({ value, label: value }))} /></Form.Item><Title level={5}>输入参数</Title>{Object.entries(currentVersion.input_schema.properties ?? {}).map(([name, schema]) => <Form.Item key={name} name={['input', name]} label={schema.description || name} rules={[{ required: currentVersion.input_schema.required?.includes(name) }]}>{inputForSchema(schema)}</Form.Item>)}<Button type="primary" loading={execute.isPending} disabled={!detail.data?.enabled || detail.data.approval_status !== 'APPROVED'} onClick={() => execute.mutate()}>运行 Skill</Button></Form>{selectedRun && <RunDetail run={selectedRun} />}</Space> : <Alert type="warning" message="缺少 copilot:skill:run 权限" /> },
        { key: 'history', label: `运行历史 (${runs.data?.length ?? 0})`, children: <Table rowKey="id" loading={runs.isPending} dataSource={runs.data ?? []} pagination={{ pageSize: 10 }} expandable={{ expandedRowRender: (run) => <RunDetail run={run} /> }} columns={[{ title: 'Run ID', dataIndex: 'id' }, { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={value === 'SUCCEEDED' ? 'green' : value === 'FAILED' ? 'red' : 'blue'}>{value}</Tag> }, { title: '版本', dataIndex: 'skill_version' }, { title: '开始', dataIndex: 'started_at' }, { title: '错误', dataIndex: 'safe_error', ellipsis: true }]} /> },
      ]} /> : <Empty description="Skill 当前版本不存在" />}
    </Drawer>
    <Modal width={860} title={versionDiff ? `版本 Diff：v${versionDiff.from_version} → v${versionDiff.to_version}` : '版本 Diff'} open={versionDiff != null} onCancel={() => setVersionDiff(undefined)} footer={null}>
      {versionDiff ? <Space direction="vertical" className="w-full"><div>变更字段：{versionDiff.changed_fields.join('、') || '无'}</div><pre className="max-h-[520px] overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-100">{versionDiff.instructions_diff.join('\n') || 'Instructions 无变化'}</pre></Space> : null}
    </Modal>
    <Modal width={820} title="创建待审核 SkillVersion" open={versionOpen} onCancel={() => setVersionOpen(false)} confirmLoading={saveVersion.isPending} onOk={() => versionForm.validateFields().then(({ version_json }) => saveVersion.mutate(JSON.parse(version_json)))}>
      <Alert className="mb-3" type="warning" showIcon message="新版本默认待审核且 Skill 会停用" description="已运行任务继续使用原固定版本；编辑不会覆盖已发布快照。" />
      <Form form={versionForm} layout="vertical"><Form.Item name="version_json" label="完整版本 JSON" rules={[{ required: true }]}><Input.TextArea rows={18} /></Form.Item></Form>
    </Modal>
  </>;
}
