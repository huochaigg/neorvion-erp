import { DEFAULT_PAGE_SIZE, knowledgeAuditLogsQueryKey, type KnowledgeAuditLog } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Input, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { fetchAuditLogs } from '@/api/ops';
import { AppTable, EllipsisCell } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function AuditLogsPage() {
  const { tenantId } = usePermissions();
  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: knowledgeAuditLogsQueryKey(tenantId, { action, page, pageSize: DEFAULT_PAGE_SIZE }),
    queryFn: ({ signal }) => fetchAuditLogs({ action, page, pageSize: DEFAULT_PAGE_SIZE }, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<KnowledgeAuditLog> = [
    { title: '时间', dataIndex: 'created_at', width: 180, render: (value: string) => formatDateTime(value) },
    { title: '动作', dataIndex: 'action', width: 180 },
    { title: '资源', dataIndex: 'resource_type', width: 120 },
    { title: '资源 ID', dataIndex: 'resource_id', width: 90 },
    { title: '用户', dataIndex: 'actor_user_id', width: 80 },
    {
      title: '详情',
      dataIndex: 'detail',
      ellipsis: true,
      render: (value: Record<string, unknown> | null) => (
        <EllipsisCell value={value ? JSON.stringify(value) : '-'} />
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader title="操作日志" description="知识库、文档、授权与 API Key 的审计记录。敏感字段已脱敏。" />
      <ListToolbar>
        <Space>
          <Input
            allowClear
            placeholder="按动作筛选，例如 document.replace"
            value={action}
            onChange={(event) => {
              setAction(event.target.value);
              setPage(1);
            }}
            style={{ width: 280 }}
          />
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          pagination={{ current: page, pageSize: DEFAULT_PAGE_SIZE, total: query.data?.total ?? 0, onChange: setPage }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
