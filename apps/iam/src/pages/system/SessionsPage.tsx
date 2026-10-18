import { ApiError } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { fetchSessions, revokeAllSessions, revokeSession, type AuthSessionInfo } from '@/api/sessions';
import { ActionCell, AppTable, EllipsisCell } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

export function SessionsPage(_props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['iam', 'sessions'],
    queryFn: ({ signal }) => fetchSessions(signal),
  });
  const revokeOne = useMutation({
    mutationFn: revokeSession,
    onSuccess: async () => {
      message.success('已撤销该会话');
      await queryClient.invalidateQueries({ queryKey: ['iam', 'sessions'] });
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '撤销失败');
    },
  });
  const revokeAll = useMutation({
    mutationFn: revokeAllSessions,
    onSuccess: async () => {
      message.success('已退出所有设备，请重新登录');
      await queryClient.invalidateQueries({ queryKey: ['iam', 'sessions'] });
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '操作失败');
    },
  });

  const columns: ColumnsType<AuthSessionInfo> = [
    {
      title: '设备',
      dataIndex: 'user_agent',
      render: (value: string) => <EllipsisCell value={value || '未知设备'} />,
    },
    { title: 'IP', dataIndex: 'ip_address', width: 140, render: (value: string) => value || '-' },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '最近活动',
      dataIndex: 'last_seen_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '失效时间',
      dataIndex: 'expires_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '状态',
      width: 140,
      render: (_, row) => {
        if (row.revoked_at) {
          return <Tag>{row.revoke_reason || '已撤销'}</Tag>;
        }
        if (row.current) {
          return <Tag color="success">当前会话</Tag>;
        }
        return <Tag color="processing">有效</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, row) =>
        row.revoked_at ? null : (
          <ActionCell>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => {
                modal.confirm({
                  title: '撤销该登录会话？',
                  content: row.current ? '将退出当前设备，需要重新登录。' : '该设备将立即无法刷新令牌。高风险操作会马上拒绝。',
                  onOk: () => revokeOne.mutateAsync(row.id),
                });
              }}
            >
              撤销
            </Button>
          </ActionCell>
        ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader
        title="登录会话"
        description="查看并撤销设备会话。Access Token 仍短期有效；已撤销会话的敏感操作会在线拒绝。"
      />
      <ListToolbar>
        <Button
          danger
          onClick={() => {
            modal.confirm({
              title: '退出所有设备？',
              content: '所有 Refresh Token 将失效，需要重新登录。',
              onOk: () => revokeAll.mutateAsync(),
            });
          }}
        >
          退出所有设备
        </Button>
      </ListToolbar>
      <ListTableArea>
        <AppTable rowKey="id" loading={query.isLoading} columns={columns} dataSource={query.data ?? []} />
      </ListTableArea>
    </ListPageContainer>
  );
}
