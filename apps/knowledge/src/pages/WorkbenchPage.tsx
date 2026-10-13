import {
  knowledgeDocumentStatusLabel,
  knowledgeOverviewQueryKey,
  knowledgeTaskStatusLabel,
  knowledgeTaskTypeLabel,
  PERMISSION_CODE,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Empty, Result, Space, Spin, Statistic, Table, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { fetchKnowledgeOverview } from '@/api/documents';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function WorkbenchPage() {
  const navigate = useNavigate();
  const { tenantId } = usePermissions();
  const query = useQuery({
    queryKey: knowledgeOverviewQueryKey(tenantId),
    queryFn: ({ signal }) => fetchKnowledgeOverview(signal),
    enabled: tenantId != null,
    refetchInterval: (current) => {
      const pending = current.state.data?.pending_task_count ?? 0;
      return pending > 0 ? 3000 : false;
    },
  });

  if (query.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (query.isError) {
    return <Result status="error" title="工作台加载失败" extra={<Button onClick={() => query.refetch()}>重试</Button>} />;
  }
  const data = query.data;
  if (!data) {
    return <Empty description="暂无数据" />;
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <PageHeader title="工作台" description="当前企业的知识库、文档与处理任务概览。统计已按租户隔离。" />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card size="small">
          <Statistic title="知识库" value={data.knowledge_base_count} />
        </Card>
        <Card size="small">
          <Statistic title="文档" value={data.document_count} />
        </Card>
        <Card size="small">
          <Statistic title="可用切片" value={data.chunk_count} />
        </Card>
        <Card size="small">
          <Statistic title="处理成功 / 失败" value={`${data.document_completed} / ${data.document_failed}`} />
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="最近上传"
          extra={
            <Button type="link" onClick={() => navigate('/bases')}>
              知识库
            </Button>
          }
        >
          {data.recent_documents.length === 0 ? (
            <Empty description="暂无文档" />
          ) : (
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={data.recent_documents}
              columns={[
                { title: '文件', dataIndex: 'filename', ellipsis: true },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 100,
                  render: (value: string) => <Tag>{knowledgeDocumentStatusLabel(value)}</Tag>,
                },
                {
                  title: '时间',
                  dataIndex: 'created_at',
                  width: 170,
                  render: (value: string) => formatDateTime(value),
                },
              ]}
              onRow={(record) => ({
                onClick: () => navigate(`/bases/${record.knowledge_base_id}/documents/${record.id}`),
              })}
            />
          )}
        </Card>
        <Card
          title="待处理 / 失败任务"
          extra={
            <Button type="link" onClick={() => navigate('/tasks')}>
              全部任务
            </Button>
          }
        >
          {data.pending_tasks.length === 0 ? (
            <Empty description="没有待处理任务" />
          ) : (
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={data.pending_tasks}
              columns={[
                {
                  title: '类型',
                  dataIndex: 'task_type',
                  width: 80,
                  render: (value: string) => knowledgeTaskTypeLabel(value),
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 90,
                  render: (value: string) => <Tag>{knowledgeTaskStatusLabel(value)}</Tag>,
                },
                { title: '进度', dataIndex: 'progress', width: 70, render: (value: number) => `${value}%` },
                {
                  title: '',
                  key: 'go',
                  width: 80,
                  render: (_, record) => (
                    <Space>
                      <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(`/bases/${record.knowledge_base_id}/documents/${record.document_id}`)}
                      >
                        查看
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          )}
        </Card>
      </div>
      <Space className="mt-4" wrap>
        <Can permission={PERMISSION_CODE.knowledgeCreate}>
          <Button type="primary" onClick={() => navigate('/bases')}>
            去知识库上传文档
          </Button>
        </Can>
        <Button onClick={() => navigate('/search')}>智能搜索</Button>
        <Button onClick={() => navigate('/chat')}>知识问答</Button>
        <Button onClick={() => navigate('/retrieval-test')}>检索测试</Button>
      </Space>
    </div>
  );
}
