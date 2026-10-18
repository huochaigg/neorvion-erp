import { PERMISSION_CODE } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { disableUser, fetchUsers, type IamUser } from '@/api/users';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

export function UsersPage(_props: PageProps) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [q, setQ] = useState('');
  const usersQuery = useQuery({
    queryKey: ['iam', 'users', q],
    queryFn: ({ signal }) => fetchUsers(q, signal),
  });
  const disableMutation = useMutation({
    mutationFn: disableUser,
    onSuccess: async () => {
      message.success('已更新用户状态');
      await queryClient.invalidateQueries({ queryKey: ['iam', 'users'] });
    },
  });

  const columns: ColumnsType<IamUser> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '邮箱', dataIndex: 'email' },
    { title: '名称', dataIndex: 'display_name' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (status: string) => <Tag color={status === 'ACTIVE' ? 'success' : 'error'}>{status}</Tag>,
    },
    {
      title: '平台管理员',
      dataIndex: 'is_platform_admin',
      width: 120,
      render: (value: boolean) => (value ? '是' : '否'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, row) => (
        <Can permission={PERMISSION_CODE.iamUsersDisable}>
          <Button
            size="small"
            danger={row.status === 'ACTIVE'}
            onClick={() =>
              disableMutation.mutate({
                userId: row.id,
                status: row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE',
              })
            }
          >
            {row.status === 'ACTIVE' ? '停用' : '启用'}
          </Button>
        </Can>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title="用户管理" description="仅平台管理员可停用账号。停用后 Access Token 立即失效。" />
      <ListToolbar>
        <Space>
          <Input.Search allowClear placeholder="搜索邮箱或名称" onSearch={setQ} />
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable rowKey="id" loading={usersQuery.isLoading} columns={columns} dataSource={usersQuery.data ?? []} />
      </ListTableArea>
    </ListPageContainer>
  );
}
