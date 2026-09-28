import {
  ApiError,
  PERMISSION_CODE,
  tenantMyPermissionsQueryKey,
  tenantPermissionsQueryKey,
  tenantRolesQueryKey,
  type PermissionInfo,
  type RoleInfo,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Checkbox, Form, Input, Modal, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import {
  createRole,
  deleteRole,
  fetchPermissions,
  fetchRoles,
  updateRole,
  updateRolePermissions,
} from '@/api/roles';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

function groupPermissions(items: PermissionInfo[]) {
  const groups = new Map<string, PermissionInfo[]>();
  for (const item of items) {
    const current = groups.get(item.module) ?? [];
    current.push(item);
    groups.set(item.module, current);
  }
  return [...groups.entries()];
}

export function RolesPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [editing, setEditing] = useState<RoleInfo | 'create' | null>(null);

  useEffect(() => {
    setEditing(null);
  }, [tenantId]);

  const rolesQuery = useQuery({
    queryKey: tenantRolesQueryKey(tenantId),
    queryFn: ({ signal }) => fetchRoles(signal),
    enabled: tenantId != null,
  });
  const permissionsQuery = useQuery({
    queryKey: tenantPermissionsQueryKey(tenantId),
    queryFn: ({ signal }) => fetchPermissions(signal),
    enabled: tenantId != null,
  });

  const grouped = useMemo(
    () => groupPermissions(permissionsQuery.data ?? []),
    [permissionsQuery.data],
  );

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: tenantRolesQueryKey(tenantId) });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'members'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'member'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'context'] });
    void queryClient.invalidateQueries({ queryKey: tenantMyPermissionsQueryKey(tenantId) });
  };

  const createMutation = useMutation({
    mutationFn: createRole,
    onSuccess: () => {
      message.success('角色已创建');
      setEditing(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: {
      roleId: number;
      name: string;
      description: string;
      permission_ids: number[];
    }) =>
      Promise.all([
        updateRole(values.roleId, { name: values.name, description: values.description }),
        updateRolePermissions(values.roleId, values.permission_ids),
      ]),
    onSuccess: () => {
      message.success('角色已更新');
      setEditing(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteRole,
    onSuccess: () => {
      message.success('角色已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const columns: ColumnsType<RoleInfo> = [
    { title: '名称', dataIndex: 'name' },
    { title: '编码', dataIndex: 'code' },
    {
      title: '类型',
      dataIndex: 'is_system',
      render: (value: boolean) => <Tag>{value ? '系统' : '自定义'}</Tag>,
    },
    { title: '说明', dataIndex: 'description' },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          {record.is_system ? null : (
            <Can permission={PERMISSION_CODE.tenantRoleManage}>
              <Button type="link" size="small" onClick={() => setEditing(record)}>
                编辑
              </Button>
            </Can>
          )}
          {record.is_system ? null : (
            <Can permission={PERMISSION_CODE.tenantRoleManage}>
              <Button
                type="link"
                size="small"
                danger
                onClick={() => {
                  modal.confirm({
                    title: `删除角色 ${record.name}？`,
                    content: '仍被成员使用的角色不能删除。',
                    onOk: () => deleteMutation.mutateAsync(record.id),
                  });
                }}
              >
                删除
              </Button>
            </Can>
          )}
        </Space>
      ),
    },
  ];

  const editingRole = editing && editing !== 'create' ? editing : null;

  return (
    <div>
      <PageHeader
        title={props.title ?? '角色管理'}
        description={props.description ?? '查看系统角色，维护自定义角色与权限。'}
        extra={
          <Can permission={PERMISSION_CODE.tenantRoleManage}>
            <Button type="primary" onClick={() => setEditing('create')}>
              新建角色
            </Button>
          </Can>
        }
      />
      <Table
        rowKey="id"
        loading={rolesQuery.isLoading}
        columns={columns}
        dataSource={rolesQuery.data}
        pagination={false}
      />

      <Modal
        title={editing === 'create' ? '新建角色' : '编辑角色'}
        open={editing != null}
        onCancel={() => setEditing(null)}
        footer={null}
        destroyOnHidden
        width={640}
      >
        <Form
          layout="vertical"
          initialValues={
            editingRole
              ? {
                  name: editingRole.name,
                  code: editingRole.code,
                  description: editingRole.description,
                  permission_ids: editingRole.permissions.map((item) => item.id),
                }
              : { permission_ids: [] }
          }
          onFinish={(values: {
            name: string;
            code?: string;
            description?: string;
            permission_ids: number[];
          }) => {
            if (editing === 'create') {
              createMutation.mutate({
                name: values.name,
                code: values.code ?? '',
                description: values.description,
                permission_ids: values.permission_ids ?? [],
              });
              return;
            }
            if (editingRole) {
              updateMutation.mutate({
                roleId: editingRole.id,
                name: values.name,
                description: values.description ?? '',
                permission_ids: values.permission_ids ?? [],
              });
            }
          }}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          {editing === 'create' ? (
            <Form.Item name="code" label="编码" rules={[{ required: true, message: '请输入编码' }]}>
              <Input placeholder="如 DUTY" />
            </Form.Item>
          ) : null}
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="permission_ids" label="权限">
            <Checkbox.Group className="w-full">
              <div className="flex flex-col gap-3">
                {grouped.map(([module, items]) => (
                  <div key={module}>
                    <p className="mb-1 font-medium">{module}</p>
                    <div className="flex flex-wrap gap-2">
                      {items.map((item) => (
                        <Checkbox key={item.id} value={item.id}>
                          {item.name}
                        </Checkbox>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Checkbox.Group>
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={createMutation.isPending || updateMutation.isPending}
            block
          >
            保存
          </Button>
        </Form>
      </Modal>
    </div>
  );
}
