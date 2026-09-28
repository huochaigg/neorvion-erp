import {
  ApiError,
  DEFAULT_PAGE_SIZE,
  grantableRoles,
  MEMBER_STATUS,
  memberRoleNames,
  PERMISSION_CODE,
  tenantMemberQueryKey,
  tenantMembersQueryKey,
  tenantMyPermissionsQueryKey,
  tenantRolesQueryKey,
  type TenantMember,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, Modal, Radio, Select, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  addMember,
  createMemberAccount,
  fetchMember,
  fetchMembers,
  removeMember,
  updateMemberRoles,
  updateMemberStatus,
} from '@/api/members';
import { fetchRoles } from '@/api/roles';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

type AddMode = 'existing' | 'create';

export function MembersPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const params = useParams();
  const routeMemberId = params.memberId ? Number(params.memberId) : null;
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [addOpen, setAddOpen] = useState(false);
  const [addMode, setAddMode] = useState<AddMode>('existing');
  const [editing, setEditing] = useState<TenantMember | null>(null);
  const [detailId, setDetailId] = useState<number | null>(routeMemberId);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);

  useEffect(() => {
    setAddOpen(false);
    setEditing(null);
    setAddMode('existing');
    setTemporaryPassword(null);
    setQ('');
    setKeyword('');
    setStatus(undefined);
    setPage(1);
  }, [tenantId]);

  useEffect(() => {
    setDetailId(routeMemberId && Number.isFinite(routeMemberId) ? routeMemberId : null);
  }, [routeMemberId]);

  const membersQuery = useQuery({
    queryKey: tenantMembersQueryKey(tenantId, { q: keyword, status, page, pageSize }),
    queryFn: ({ signal }) =>
      fetchMembers(tenantId as number, { q: keyword, status, page, pageSize }, signal),
    enabled: tenantId != null,
  });
  const rolesQuery = useQuery({
    queryKey: tenantRolesQueryKey(tenantId),
    queryFn: ({ signal }) => fetchRoles(signal),
    enabled: tenantId != null,
  });
  const detailQuery = useQuery({
    queryKey: tenantMemberQueryKey(tenantId, detailId),
    queryFn: ({ signal }) => fetchMember(tenantId as number, detailId as number, signal),
    enabled: tenantId != null && detailId != null,
  });

  const assignableRoles = useMemo(
    () => grantableRoles(rolesQuery.data ?? []),
    [rolesQuery.data],
  );

  const invalidateMembers = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'members'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'member'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'context'] });
    void queryClient.invalidateQueries({ queryKey: tenantMyPermissionsQueryKey(tenantId) });
  };

  const addMutation = useMutation({
    mutationFn: (values: { email: string; role_ids: number[] }) =>
      addMember(tenantId as number, values),
    onSuccess: () => {
      message.success('已添加成员');
      setAddOpen(false);
      invalidateMembers();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '添加失败');
    },
  });

  const createMutation = useMutation({
    mutationFn: (values: { display_name: string; email: string; role_ids: number[] }) =>
      createMemberAccount(tenantId as number, values),
    onSuccess: (data) => {
      message.success('账号已创建');
      setAddOpen(false);
      setTemporaryPassword(data.temporary_password ?? null);
      invalidateMembers();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const rolesMutation = useMutation({
    mutationFn: (values: { memberId: number; role_ids: number[] }) =>
      updateMemberRoles(tenantId as number, values.memberId, { role_ids: values.role_ids }),
    onSuccess: () => {
      message.success('角色已更新');
      setEditing(null);
      invalidateMembers();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const statusMutation = useMutation({
    mutationFn: (values: { memberId: number; status: string }) =>
      updateMemberStatus(tenantId as number, values.memberId, values.status),
    onSuccess: () => {
      message.success('状态已更新');
      invalidateMembers();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const removeMutation = useMutation({
    mutationFn: (memberId: number) => removeMember(tenantId as number, memberId),
    onSuccess: () => {
      message.success('已移出企业');
      invalidateMembers();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '移除失败');
    },
  });

  const copyTemporaryPassword = async () => {
    if (!temporaryPassword) {
      return;
    }
    try {
      await navigator.clipboard.writeText(temporaryPassword);
      message.success('已复制');
    } catch {
      message.error('复制失败，请手动选择');
    }
  };

  const columns: ColumnsType<TenantMember> = [
    { title: '成员', dataIndex: 'display_name' },
    { title: '邮箱', dataIndex: 'email' },
    {
      title: '角色',
      dataIndex: 'roles',
      render: memberRoleNames,
    },
    {
      title: '状态',
      dataIndex: 'status',
      render: (value: string) => (
        <Tag color={value === MEMBER_STATUS.active ? 'success' : 'default'}>
          {value === MEMBER_STATUS.active ? '启用' : '禁用'}
        </Tag>
      ),
    },
    { title: '加入时间', dataIndex: 'joined_at' },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space wrap>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setDetailId(record.id);
              navigate(`/system/members/${record.id}`);
            }}
          >
            查看
          </Button>
          {record.is_owner ? null : (
            <Can permission={PERMISSION_CODE.tenantMemberManage}>
              <Button type="link" size="small" onClick={() => setEditing(record)}>
                编辑角色
              </Button>
            </Can>
          )}
          {record.is_owner ? null : (
            <Can permission={PERMISSION_CODE.tenantMemberManage}>
              <Button
                type="link"
                size="small"
                danger={record.status === MEMBER_STATUS.active}
                onClick={() => {
                  const next =
                    record.status === MEMBER_STATUS.active
                      ? MEMBER_STATUS.disabled
                      : MEMBER_STATUS.active;
                  modal.confirm({
                    title: next === MEMBER_STATUS.disabled ? '禁用该成员？' : '启用该成员？',
                    content:
                      next === MEMBER_STATUS.disabled
                        ? '禁用后该成员立即无法进入本企业，成员记录仍保留。'
                        : '启用后该成员可再次进入本企业。',
                    onOk: () => statusMutation.mutateAsync({ memberId: record.id, status: next }),
                  });
                }}
              >
                {record.status === MEMBER_STATUS.active ? '禁用' : '启用'}
              </Button>
            </Can>
          )}
          {record.is_owner ? null : (
            <Can permission={PERMISSION_CODE.tenantMemberManage}>
              <Button
                type="link"
                size="small"
                danger
                onClick={() => {
                  modal.confirm({
                    title: `将 ${record.display_name} 移出企业？`,
                    content: '会解除本企业成员关系并删除角色授权，不会删除其全局登录账号。',
                    onOk: () => removeMutation.mutateAsync(record.id),
                  });
                }}
              >
                移除
              </Button>
            </Can>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={props.title ?? '成员管理'}
        description={props.description ?? '添加已有账号或创建新账号，分配角色并启停、移除成员。'}
        extra={
          <Can permission={PERMISSION_CODE.tenantMemberManage}>
            <Button type="primary" onClick={() => setAddOpen(true)}>
              添加成员
            </Button>
          </Can>
        }
      />
      <Space className="mb-4" wrap>
        <Input.Search
          allowClear
          placeholder="搜索姓名或邮箱"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          onSearch={(value) => {
            setKeyword(value.trim());
            setPage(1);
          }}
          style={{ width: 240 }}
        />
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 140 }}
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={[
            { value: MEMBER_STATUS.active, label: '启用' },
            { value: MEMBER_STATUS.disabled, label: '禁用' },
          ]}
        />
      </Space>
      <Table
        rowKey="id"
        loading={membersQuery.isLoading}
        columns={columns}
        dataSource={membersQuery.data?.items}
        pagination={{
          current: page,
          pageSize,
          total: membersQuery.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage);
            setPageSize(nextSize);
          },
        }}
      />

      <Modal
        title="添加成员"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Radio.Group
          className="mb-4"
          value={addMode}
          onChange={(event) => setAddMode(event.target.value)}
          optionType="button"
          options={[
            { label: '已有账号', value: 'existing' },
            { label: '创建新账号', value: 'create' },
          ]}
        />
        {addMode === 'existing' ? (
          <Form
            layout="vertical"
            onFinish={(values: { email: string; role_ids?: number[] }) =>
              addMutation.mutate({ email: values.email, role_ids: values.role_ids ?? [] })
            }
          >
            <Form.Item
              name="email"
              label="邮箱"
              rules={[
                { required: true, message: '请输入已注册用户的邮箱' },
                { type: 'email', message: '邮箱格式不正确' },
              ]}
            >
              <Input placeholder="user@example.com" />
            </Form.Item>
            <Form.Item name="role_ids" label="角色">
              <Select
                mode="multiple"
                placeholder="不选则默认为只读"
                options={assignableRoles.map((role) => ({
                  value: role.id,
                  label: `${role.name}（${role.code}）`,
                }))}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={addMutation.isPending} block>
              提交
            </Button>
          </Form>
        ) : (
          <Form
            layout="vertical"
            onFinish={(values: { display_name: string; email: string; role_ids?: number[] }) =>
              createMutation.mutate({
                display_name: values.display_name,
                email: values.email,
                role_ids: values.role_ids ?? [],
              })
            }
          >
            <Form.Item
              name="display_name"
              label="显示名称"
              rules={[{ required: true, message: '请输入显示名称' }]}
            >
              <Input placeholder="张三" />
            </Form.Item>
            <Form.Item
              name="email"
              label="邮箱"
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '邮箱格式不正确' },
              ]}
            >
              <Input placeholder="new@example.com" />
            </Form.Item>
            <Form.Item name="role_ids" label="角色">
              <Select
                mode="multiple"
                placeholder="不选则默认为只读"
                options={assignableRoles.map((role) => ({
                  value: role.id,
                  label: `${role.name}（${role.code}）`,
                }))}
              />
            </Form.Item>
            <Typography.Paragraph className="text-xs text-slate-500">
              系统会生成一次性临时密码，成功后只展示一次。管理员不能设定长期密码。
            </Typography.Paragraph>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending} block>
              创建账号
            </Button>
          </Form>
        )}
      </Modal>

      <Modal
        title="临时密码"
        open={Boolean(temporaryPassword)}
        closable={false}
        maskClosable={false}
        footer={
          <Button type="primary" onClick={() => setTemporaryPassword(null)}>
            我已保存
          </Button>
        }
      >
        <Typography.Paragraph>
          请立即复制并交给该成员。关闭后无法再次查看明文密码。
        </Typography.Paragraph>
        <Space.Compact className="w-full">
          <Input readOnly value={temporaryPassword ?? ''} />
          <Button onClick={() => void copyTemporaryPassword()}>复制</Button>
        </Space.Compact>
      </Modal>

      <Modal
        title="修改角色"
        open={Boolean(editing)}
        onCancel={() => setEditing(null)}
        footer={null}
        destroyOnHidden
      >
        {editing ? (
          <Form
            layout="vertical"
            initialValues={{ role_ids: editing.roles.map((item) => item.id) }}
            onFinish={(values: { role_ids: number[] }) =>
              rolesMutation.mutate({ memberId: editing.id, role_ids: values.role_ids ?? [] })
            }
          >
            <Form.Item name="role_ids" label="角色">
              <Select
                mode="multiple"
                options={assignableRoles.map((role) => ({
                  value: role.id,
                  label: `${role.name}（${role.code}）`,
                }))}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={rolesMutation.isPending} block>
              保存
            </Button>
          </Form>
        ) : null}
      </Modal>

      <Drawer
        title="成员详情"
        open={detailId != null}
        onClose={() => {
          setDetailId(null);
          navigate('/system/members');
        }}
        width={420}
      >
        {detailQuery.isError ? (
          <p className="text-sm text-red-600">
            {detailQuery.error instanceof ApiError ? detailQuery.error.message : '无法加载成员'}
          </p>
        ) : null}
        {detailQuery.data ? (
          <div className="space-y-2 text-sm">
            <p>姓名：{detailQuery.data.display_name}</p>
            <p>邮箱：{detailQuery.data.email}</p>
            <p>角色：{memberRoleNames(detailQuery.data.roles)}</p>
            <p>状态：{detailQuery.data.status}</p>
            <p>有效权限：</p>
            <ul className="m-0 list-disc pl-5">
              {detailQuery.data.permissions.map((item) => (
                <li key={item.code}>
                  {item.name}（{item.code}）
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
