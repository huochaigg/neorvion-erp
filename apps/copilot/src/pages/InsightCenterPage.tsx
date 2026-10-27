import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Empty, Form, Input, InputNumber, Modal, Select, Space, Statistic, Switch, Table, Tabs, Tag, Typography } from 'antd';
import { useState } from 'react';
import { acknowledgeInsight, closeInsight, createInsightRule, getInsightDashboard, listInsightNotifications, listInsightRules, listInsightRuns, listInsights, patchInsightRule, readInsightNotification, runInsightRule, type BusinessInsight, type InsightNotification, type InsightRule, type InsightRun } from '@/api/insights';
import { useCopilotStore } from '@/store';

const { Text, Title } = Typography;

export default function InsightCenterPage() {
  const tenantId = useCopilotStore((s) => s.tenantId);
  const query = useQueryClient();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<BusinessInsight>();
  const [form] = Form.useForm();
  const key = ['tenant', tenantId, 'insights'];
  const dashboard = useQuery({ queryKey: [...key, 'dashboard'], queryFn: ({ signal }) => getInsightDashboard(signal), enabled: tenantId != null });
  const rules = useQuery({ queryKey: [...key, 'rules'], queryFn: ({ signal }) => listInsightRules(signal), enabled: tenantId != null });
  const insights = useQuery({ queryKey: [...key, 'list'], queryFn: ({ signal }) => listInsights(signal), enabled: tenantId != null });
  const runs = useQuery({ queryKey: [...key, 'runs'], queryFn: ({ signal }) => listInsightRuns(signal), enabled: tenantId != null });
  const notifications = useQuery({ queryKey: [...key, 'notifications'], queryFn: ({ signal }) => listInsightNotifications(signal), enabled: tenantId != null });
  const refresh = () => void query.invalidateQueries({ queryKey: key });
  const create = useMutation({ mutationFn: createInsightRule, onSuccess: () => { setOpen(false); form.resetFields(); refresh(); } });
  const run = useMutation({ mutationFn: runInsightRule, onSuccess: refresh });
  const toggle = useMutation({ mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => patchInsightRule(id, { enabled }), onSuccess: refresh });
  const action = useMutation({ mutationFn: ({ id, kind }: { id: number; kind: 'ack' | 'close' }) => kind === 'ack' ? acknowledgeInsight(id) : closeInsight(id), onSuccess: refresh });
  const read = useMutation({ mutationFn: readInsightNotification, onSuccess: refresh });
  const counts = dashboard.data?.severity ?? {};
  const rulesData = (rules.data as { items?: InsightRule[] } | undefined)?.items ?? [];
  return <div className="space-y-4 p-5">
    <div><Title level={3} className="!mb-1">主动洞察中心</Title><Text type="secondary">确定性规则发现异常，AI 仅负责解释；不会自动修改 ERP。</Text></div>
    <Alert type="info" showIcon message="安全执行边界" description="定时后台身份尚未建立，因此当前仅允许用户主动运行，并使用本次请求的短期只读权限。" />
    <div className="grid gap-3 sm:grid-cols-4 mt-4"><Card><Statistic title="待处理" value={dashboard.data?.open_total ?? 0} /></Card>{['HIGH', 'MEDIUM', 'LOW'].map((x) => <Card key={x}><Statistic title={x} value={counts[x] ?? 0} /></Card>)}</div>
    <Tabs items={[
      { key: 'insights', label: '预警', children: (insights.data?.items.length ?? 0) ? <Table<BusinessInsight> rowKey="id" dataSource={insights.data?.items} pagination={{ pageSize: 10 }} columns={[{ title: '类型', dataIndex: 'detector_type' }, { title: '资源', render: (_, x) => `${x.resource_type} #${x.resource_id}` }, { title: '级别', dataIndex: 'severity', render: (x) => <Tag color={x === 'HIGH' ? 'red' : 'orange'}>{x}</Tag> }, { title: '状态', dataIndex: 'status' }, { title: '操作', render: (_, x) => <Space><Button size="small" onClick={() => setDetail(x)}>详情</Button><Button size="small" onClick={() => action.mutate({ id: x.id, kind: 'ack' })}>知悉</Button><Button size="small" onClick={() => action.mutate({ id: x.id, kind: 'close' })}>关闭提醒</Button></Space> }]} /> : <Empty description="尚无业务预警" /> },
      { key: 'rules', label: '规则', children: <Card extra={<Button type="primary" onClick={() => setOpen(true)}>新建规则</Button>}>{rulesData.length ? <Table<InsightRule> rowKey="id" dataSource={rulesData} pagination={false} columns={[{ title: '名称', dataIndex: 'name' }, { title: '检测器', dataIndex: 'detector_type' }, { title: '周期(分钟)', dataIndex: 'interval_minutes' }, { title: '启用', render: (_, x) => <Switch checked={x.enabled} onChange={(enabled) => toggle.mutate({ id: x.id, enabled })} /> }, { title: '操作', render: (_, x) => <Button size="small" loading={run.isPending} onClick={() => run.mutate(x.id)}>立即运行</Button> }]} /> : <Empty description="尚无洞察规则" />}</Card> },
      { key: 'runs', label: '运行历史', children: <Table<InsightRun> rowKey="id" dataSource={runs.data?.items ?? []} pagination={{ pageSize: 10 }} columns={[{ title: 'Run', dataIndex: 'id' }, { title: '状态', dataIndex: 'status' }, { title: '发现', dataIndex: 'detected_count' }, { title: '去重', dataIndex: 'duplicate_count' }, { title: '错误', dataIndex: 'safe_error' }]} /> },
      { key: 'notifications', label: '站内通知', children: <Table<InsightNotification> rowKey="id" dataSource={notifications.data?.items ?? []} pagination={{ pageSize: 10 }} columns={[{ title: '标题', dataIndex: 'title' }, { title: '内容', dataIndex: 'safe_body' }, { title: '状态', render: (_, x) => x.read_at ? '已读' : '未读' }, { title: '操作', render: (_, x) => <Button size="small" disabled={Boolean(x.read_at)} onClick={() => read.mutate(x.id)}>标记已读</Button> }]} /> },
    ]} />
    <Modal title="新建固定检测规则" open={open} onCancel={() => setOpen(false)} onOk={() => form.validateFields().then((v) => create.mutate({ ...v, config: JSON.parse(v.config) }))} confirmLoading={create.isPending}><Form form={form} layout="vertical" initialValues={{ interval_minutes: 60, enabled: false, config: '{"threshold": 5}' }}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="detector_type" label="检测器" rules={[{ required: true }]}><Select options={['LOW_STOCK_RISK', 'OVERDUE_SHIPMENT', 'PURCHASE_ARRIVAL_DELAY', 'INVENTORY_COVERAGE_RISK'].map((value) => ({ value, label: value }))} /></Form.Item><Form.Item name="config" label="结构化配置 JSON" rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item><Form.Item name="interval_minutes" label="周期（至少15分钟）"><InputNumber min={15} /></Form.Item><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Form></Modal>
    <Modal width={760} title="预警详情" open={Boolean(detail)} onCancel={() => setDetail(undefined)} footer={null}>{detail ? <Descriptions bordered column={1} items={[{ key: 'type', label: '检测器', children: detail.detector_type }, { key: 'resource', label: '业务资源', children: `${detail.resource_type} #${detail.resource_id}` }, { key: 'state', label: '状态', children: detail.status }, { key: 'evidence', label: '数值证据', children: <pre className="whitespace-pre-wrap">{JSON.stringify(detail.evidence_summary, null, 2)}</pre> }, { key: 'ai', label: 'AI 分析', children: detail.ai_summary ?? '未执行；确定性预警仍然有效' }]} /> : null}</Modal>
  </div>;
}
