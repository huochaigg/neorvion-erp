import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Empty,
  Segmented,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { listExecutions } from '@/api/executions';
import { listProposals } from '@/api/proposals';
import { listWorkflows } from '@/api/workflows';
import { ExecutionDetail } from '@/components/ExecutionDetail';
import { ExecutionStatus } from '@/components/ExecutionStatus';
import { ApprovalListPage } from '@/pages/ApprovalListPage';
import { ProposalListPage } from '@/pages/ProposalListPage';
import { WorkflowListPage } from '@/pages/WorkflowListPage';
import { useCopilotStore } from '@/store';
import type { ActionExecution } from '@/types';

const { Text, Title } = Typography;
type TabKey = 'all' | 'pending' | 'drafts' | 'approvals' | 'executions' | 'workflows';

const TAB_KEYS = new Set<TabKey>([
  'all',
  'pending',
  'drafts',
  'approvals',
  'executions',
  'workflows',
]);

export default function TaskCenterPage() {
  const tenantId = useCopilotStore((s) => s.tenantId);
  const [params, setParams] = useSearchParams();
  const requestedTab = params.get('tab') as TabKey | null;
  const tab: TabKey = requestedTab && TAB_KEYS.has(requestedTab) ? requestedTab : 'all';
  const proposals = useQuery({
    queryKey: ['tenant', tenantId, 'action-proposals'],
    queryFn: ({ signal }) => listProposals(signal),
    enabled: tenantId != null,
  });
  const executions = useQuery({
    queryKey: ['tenant', tenantId, 'action-executions'],
    queryFn: ({ signal }) => listExecutions(signal),
    enabled: tenantId != null,
  });
  const workflows = useQuery({
    queryKey: ['tenant', tenantId, 'workflows'],
    queryFn: ({ signal }) => listWorkflows(signal),
    enabled: tenantId != null,
  });
  const [executionId, setExecutionId] = useState<number>();
  const rows = useMemo(
    () =>
      [
        ...(proposals.data?.items ?? []).map((x) => ({
          key: `proposal-${x.id}`,
          id: x.id,
          title: `业务草稿 #${x.id}`,
          type: x.action_type,
          source: '业务草稿',
          status: x.status,
          updated_at: x.updated_at,
          action: 'draft' as const,
        })),
        ...(executions.data?.items ?? []).map((x) => ({
          key: `execution-${x.id}`,
          id: x.id,
          title: `执行任务 #${x.id}`,
          type: x.action_type,
          source: '审批与执行',
          status: x.status,
          updated_at: x.updated_at,
          action: 'execution' as const,
        })),
        ...(workflows.data?.items ?? []).map((x) => ({
          key: `workflow-${x.id}`,
          id: x.id,
          title: `业务流程 #${x.id}`,
          type: x.workflow_type,
          source: '业务流程',
          status: x.status,
          updated_at: x.updated_at,
          action: 'workflow' as const,
        })),
      ].sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    [executions.data?.items, proposals.data?.items, workflows.data?.items],
  );
  const switchTab = (value: string | number) =>
    setParams(value === 'all' ? {} : { tab: String(value) });
  return (
    <div className="copilot-scroll h-full overflow-y-auto p-4 md:p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-4">
          <Title level={3} className="!mb-1">
            我的任务
          </Title>
          <Text type="secondary">
            在一个工作区查看草稿、审批执行与业务流程；底层仍使用原 V5–V7 状态机。
          </Text>
        </div>
        <Segmented
          block
          value={tab}
          onChange={switchTab}
          options={[
            { label: '全部任务', value: 'all' },
            { label: '待我处理', value: 'pending' },
            { label: '业务草稿', value: 'drafts' },
            { label: '审批任务', value: 'approvals' },
            { label: '执行记录', value: 'executions' },
            { label: '流程进度', value: 'workflows' },
          ]}
        />
        <div className="mt-4">
          {tab === 'all' ? (
            <>
              <div className="mb-4 grid gap-3 sm:grid-cols-3">
                <Card>
                  <Statistic title="业务草稿" value={proposals.data?.total ?? 0} />
                </Card>
                <Card>
                  <Statistic title="审批与执行" value={executions.data?.total ?? 0} />
                </Card>
                <Card>
                  <Statistic title="业务流程" value={workflows.data?.total ?? 0} />
                </Card>
              </div>
              <Alert
                className="mb-3"
                type="info"
                showIcon
                message="跨模块汇总说明"
                description="列表聚合各来源当前已加载结果，用于工作概览；各模块保持独立分页与状态，不宣称全局精确分页。"
              />
              {rows.length ? (
                <Table
                  rowKey="key"
                  dataSource={rows}
                  pagination={{ pageSize: 12 }}
                  columns={[
                    { title: '任务', dataIndex: 'title' },
                    { title: '类型', dataIndex: 'type', ellipsis: true },
                    { title: '来源', dataIndex: 'source' },
                    { title: '状态', dataIndex: 'status', render: (x) => <Tag>{x}</Tag> },
                    {
                      title: '更新时间',
                      dataIndex: 'updated_at',
                      render: (x) => new Date(x).toLocaleString(),
                    },
                    {
                      title: '操作',
                      render: (_, x) => (
                        <Button
                          size="small"
                          onClick={() =>
                            x.action === 'execution'
                              ? setExecutionId(x.id)
                              : switchTab(x.action === 'draft' ? 'drafts' : 'workflows')
                          }
                        >
                          查看
                        </Button>
                      ),
                    },
                  ]}
                />
              ) : (
                <Empty description="暂无任务" />
              )}
            </>
          ) : tab === 'pending' || tab === 'approvals' ? (
            <ApprovalListPage />
          ) : tab === 'drafts' ? (
            <ProposalListPage />
          ) : tab === 'executions' ? (
            <ExecutionListPanel rows={executions.data?.items ?? []} onOpen={setExecutionId} />
          ) : (
            <WorkflowListPage />
          )}
        </div>
        {executionId ? (
          <ExecutionDetail id={executionId} open onClose={() => setExecutionId(undefined)} />
        ) : null}
      </div>
    </div>
  );
}

function ExecutionListPanel({
  rows,
  onOpen,
}: {
  rows: ActionExecution[];
  onOpen: (id: number) => void;
}) {
  return (
    <Card title="执行记录">
      {rows.length ? (
        <Table
          rowKey="id"
          dataSource={rows}
          pagination={{ pageSize: 12 }}
          columns={[
            { title: '执行', render: (_, x) => `#${x.id}` },
            { title: '业务类型', dataIndex: 'action_type' },
            { title: '状态', dataIndex: 'status', render: (x) => <ExecutionStatus value={x} /> },
            { title: 'ERP 单据', render: (_, x) => x.erp_resource_no ?? x.erp_resource_id ?? '-' },
            {
              title: '操作',
              render: (_, x) => (
                <Space>
                  <Button size="small" onClick={() => onOpen(x.id)}>
                    结果与审计
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      ) : (
        <Empty description="暂无执行记录" />
      )}
    </Card>
  );
}
