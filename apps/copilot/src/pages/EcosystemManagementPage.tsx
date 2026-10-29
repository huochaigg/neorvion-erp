import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Form, Input, Modal, Space, Table, Tabs, Tag, Typography } from 'antd';
import { useState } from 'react';
import {
  createMcpServer, createSkill, discoverMcpTools, listMcpServers, listMcpTools,
  listSkills, probeMcpServer, reviewMcpServer, reviewMcpTool, reviewSkill,
  setMcpServerEnabled,
} from '@/api/ecosystem';

const { Paragraph, Text } = Typography;

interface Props { canMcpRead: boolean; canMcpManage: boolean; canSkillRead: boolean; canSkillManage: boolean }

export default function EcosystemManagementPage({ canMcpRead, canMcpManage, canSkillRead, canSkillManage }: Props) {
  const queryClient = useQueryClient();
  const [serverOpen, setServerOpen] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);
  const [serverForm] = Form.useForm();
  const [skillForm] = Form.useForm();
  const servers = useQuery({ queryKey: ['mcp-servers'], queryFn: ({ signal }) => listMcpServers(signal), enabled: canMcpRead });
  const tools = useQuery({ queryKey: ['mcp-tools'], queryFn: ({ signal }) => listMcpTools(signal), enabled: canMcpRead });
  const skills = useQuery({ queryKey: ['agent-skills'], queryFn: ({ signal }) => listSkills(signal), enabled: canSkillRead });
  const refresh = async () => {
    await Promise.all(['mcp-servers', 'mcp-tools', 'agent-skills'].map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
  };
  const action = useMutation({ mutationFn: (work: () => Promise<unknown>) => work(), onSuccess: refresh });
  const submitServer = async () => {
    const values = await serverForm.validateFields();
    await createMcpServer({ ...values, transport_type: 'STREAMABLE_HTTP', authentication_type: values.credential_reference ? 'BEARER_ENV' : 'NONE', allowed_tools: [], denied_tools: [], allowed_resources: {}, timeout_seconds: 10, max_retries: 1, concurrency_limit: 2 });
    setServerOpen(false); serverForm.resetFields(); await refresh();
  };
  const submitSkill = async () => {
    const values = await skillForm.validateFields();
    await createSkill({ skill_key: values.skill_key, name: values.name, description: values.description, version: {
      instructions: values.instructions,
      input_schema: { type: 'object', properties: { query: { type: 'string', maxLength: 1000 } }, required: ['query'] },
      output_schema: { type: 'object', properties: { summary: { type: 'string', maxLength: 4000 } }, required: ['summary'] },
      allowed_agents: ['inventory_agent'], required_permissions: ['inventory:read'], allowed_tools: ['analyze_inventory_coverage'],
      required_evidence: true, risk_level: 'READ_ONLY', timeout_seconds: 30, token_budget: 3000,
    } });
    setSkillOpen(false); skillForm.resetFields(); await refresh();
  };
  return <>
    <Alert className="mb-4" type="warning" showIcon message="外部能力默认关闭" description="只有域名白名单、健康检查、人工审核、IAM 权限和 Agent 白名单同时通过后，工具才会进入模型上下文。Secret 只保存环境变量名。" />
    <Tabs items={[
      ...(canMcpRead ? [{ key: 'servers', label: 'MCP Servers', children: <Card extra={<Button disabled={!canMcpManage} onClick={() => setServerOpen(true)}>新增 Server</Button>}><Table rowKey="id" loading={servers.isPending} dataSource={servers.data ?? []} pagination={false} columns={[
        { title: 'Server', dataIndex: 'display_name' }, { title: 'Endpoint', dataIndex: 'endpoint', ellipsis: true },
        { title: '审核', dataIndex: 'approval_status', render: (value: string) => <Tag>{value}</Tag> },
        { title: '健康', dataIndex: 'health_status', render: (value: string) => <Tag>{value}</Tag> },
        { title: '操作', render: (_, row) => <Space wrap>
          <Button size="small" disabled={!canMcpManage} onClick={() => action.mutate(() => probeMcpServer(row.id))}>探测</Button>
          <Button size="small" disabled={!canMcpManage} onClick={() => action.mutate(() => discoverMcpTools(row.id))}>发现</Button>
          <Button size="small" disabled={!canMcpManage} onClick={() => action.mutate(() => reviewMcpServer(row.id, true))}>审核</Button>
          <Button size="small" disabled={!canMcpManage || row.health_status !== 'HEALTHY'} onClick={() => action.mutate(() => setMcpServerEnabled(row.id, !row.enabled))}>{row.enabled ? '停用' : '启用'}</Button>
        </Space> },
      ]} /></Card> },
      { key: 'tools', label: 'Tool Registry', children: <Card><Table rowKey="id" loading={tools.isPending} dataSource={tools.data ?? []} pagination={false} columns={[
        { title: '工具', dataIndex: 'qualified_name' }, { title: '风险', dataIndex: 'risk_level', render: (value: string) => <Tag color="green">{value}</Tag> },
        { title: 'Schema', dataIndex: 'schema_hash', render: (value: string) => <Text code>{value.slice(0, 12)}</Text> },
        { title: '状态', dataIndex: 'approval_status', render: (value: string) => <Tag>{value}</Tag> },
        { title: '操作', render: (_, row) => <Button size="small" disabled={!canMcpManage || row.approval_status === 'APPROVED'} onClick={() => action.mutate(() => reviewMcpTool(row.id, true))}>审核只读版本</Button> },
      ]} /></Card> },
      ] : []),
      ...(canSkillRead ? [{ key: 'skills', label: 'Agent Skills', children: <Card extra={<Button disabled={!canSkillManage} onClick={() => setSkillOpen(true)}>新增 Skill</Button>}><Table rowKey="id" loading={skills.isPending} dataSource={skills.data ?? []} pagination={false} columns={[
        { title: 'Skill', dataIndex: 'name' }, { title: 'Key', dataIndex: 'skill_key' }, { title: '版本', dataIndex: 'current_version' },
        { title: '状态', dataIndex: 'approval_status', render: (value: string) => <Tag>{value}</Tag> },
        { title: '操作', render: (_, row) => <Button size="small" disabled={!canSkillManage || row.approval_status === 'APPROVED'} onClick={() => action.mutate(() => reviewSkill(row.id, true))}>审核并启用</Button> },
      ]} /></Card> },
      ] : []),
    ]} />
    <Modal title="新增 MCP Server" open={serverOpen} onCancel={() => setServerOpen(false)} onOk={submitServer}><Paragraph type="secondary">Endpoint 必须先加入部署域名白名单；这里只填写 Secret 环境变量名。</Paragraph><Form layout="vertical" form={serverForm}><Form.Item name="server_key" label="Server Key" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="display_name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="description" label="说明"><Input.TextArea /></Form.Item><Form.Item name="endpoint" label="HTTPS Endpoint" rules={[{ required: true, type: 'url' }]}><Input /></Form.Item><Form.Item name="credential_reference" label="Secret 环境变量名"><Input placeholder="MCP_VENDOR_TOKEN" /></Form.Item></Form></Modal>
    <Modal title="新增只读 Skill" open={skillOpen} onCancel={() => setSkillOpen(false)} onOk={submitSkill}><Form layout="vertical" form={skillForm}><Form.Item name="skill_key" label="Skill Key" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="description" label="说明" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="instructions" label="业务指导" rules={[{ required: true, min: 10 }]}><Input.TextArea rows={6} /></Form.Item></Form></Modal>
  </>;
}
