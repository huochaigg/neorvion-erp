import { useQuery } from '@tanstack/react-query';
import type { ColumnsType } from 'antd/es/table';
import { fetchAuditLogs, type IamAuditLog } from '@/api/catalog';
import { AppTable } from '@/components/AppTable';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

export function AuditPage(_props: PageProps) {
  const query = useQuery({
    queryKey: ['iam', 'audit'],
    queryFn: ({ signal }) => fetchAuditLogs(signal),
  });
  const columns: ColumnsType<IamAuditLog> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '操作', dataIndex: 'action', width: 180 },
    { title: '对象', dataIndex: 'target_type', width: 120 },
    { title: '对象 ID', dataIndex: 'target_id', width: 120 },
    { title: '操作者', dataIndex: 'actor_user_id', width: 100 },
    { title: '租户', dataIndex: 'tenant_id', width: 100 },
    { title: '详情', dataIndex: 'detail' },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title="审计日志" description="身份、角色、应用变更只读审计。不能修改或删除。" />
      <ListTableArea>
        <AppTable rowKey="id" loading={query.isLoading} columns={columns} dataSource={query.data ?? []} />
      </ListTableArea>
    </ListPageContainer>
  );
}
