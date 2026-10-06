import {
  ApiError,
  PERMISSION_CODE,
  tenantMyPermissionsQueryKey,
  tenantPermissionTreeQueryKey,
  tenantPermissionsQueryKey,
  tenantRolesQueryKey,
  type RoleInfo,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, Modal, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  createRole,
  deleteRole,
  fetchPermissionTree,
  fetchRoles,
  updateRole,
  updateRolePermissions,
} from '@/api/roles';
import { ActionCell, AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { PermissionTree } from '@/components/PermissionTree';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

type EditorState = { type: 'create' } | { type: 'edit'; role: RoleInfo } | { type: 'perms'; role: RoleInfo };

export function RolesPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [viewing, setViewing] = useState<RoleInfo | null>(null);

  useEffect(() => {
    setEditor(null);
    setViewing(null);
  }, [tenantId]);

  const rolesQuery = useQuery({
    queryKey: tenantRolesQueryKey(tenantId),
    queryFn: ({ signal }) => fetchRoles(signal),
    enabled: tenantId != null,
  });
  const treeQuery = useQuery({
    queryKey: tenantPermissionTreeQueryKey(tenantId),
    queryFn: ({ signal }) => fetchPermissionTree(signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: tenantRolesQueryKey(tenantId) });
    void queryClient.invalidateQueries({ queryKey: tenantPermissionsQueryKey(tenantId) });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'members'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'member'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'context'] });
    void queryClient.invalidateQueries({ queryKey: tenantMyPermissionsQueryKey(tenantId) });
  };

  const createMutation = useMutation({
    mutationFn: createRole,
    onSuccess: () => {
      message.success('角色已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: { roleId: number; name: string; description: string }) =>
      updateRole(values.roleId, { name: values.name, description: values.description }),
    onSuccess: () => {
      message.success('角色已更新');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const permsMutation = useMutation({
    mutationFn: (values: { roleId: number; permission_ids: number[] }) =>
      updateRolePermissions(values.roleId, values.permission_ids),
    onSuccess: () => {
      message.success('权限已更新');
      setEditor(null);
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
    {
      title: '名称',
      dataIndex: 'name',
      width: 140,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '编码',
      dataIndex: 'code',
      width: 140,
      render: (value: string) => <CodeCell value={value} />,
    },
    {
      title: '类型',
      dataIndex: 'is_system',
      width: 100,
      render: (value: boolean) => <Tag color={value ? 'blue' : 'default'}>{value ? '系统' : '自定义'}</Tag>,
    },
    {
      title: '成员数',
      dataIndex: 'member_count',
      width: 90,
    },
    {
      title: '说明',
      dataIndex: 'description',
      width: 220,
      render: (value: string | null) => <EllipsisCell value={value} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => setViewing(record)}>
            查看
          </Button>
          {record.code === 'OWNER' ? null : (
            <Can permission={PERMISSION_CODE.tenantRolePermissionUpdate}>
              <Button type="link" size="small" onClick={() => setEditor({ type: 'perms', role: record })}>
                配置权限
              </Button>
            </Can>
          )}
          {record.is_system ? null : (
            <Can permission={PERMISSION_CODE.tenantRoleUpdate}>
              <Button type="link" size="small" onClick={() => setEditor({ type: 'edit', role: record })}>
                编辑
              </Button>
            </Can>
          )}
          {record.is_system ? null : (
            <Can permission={PERMISSION_CODE.tenantRoleDelete}>
              <Button
                type="link"
                size="small"
                danger
                onClick={() => {
                  if (record.member_count > 0) {
                    modal.warning({
                      title: '无法删除',
                      content: `当前角色仍有 ${record.member_count} 名成员使用，请先调整这些成员的角色。`,
                    });
                    return;
                  }
                  modal.confirm({
                    title: `删除角色 ${record.name}？`,
                    content: '删除后不可恢复。系统不会自动给成员换角色。',
                    onOk: () => deleteMutation.mutateAsync(record.id),
                  });
                }}
              >
                删除
              </Button>
            </Can>
          )}
        </ActionCell>
      ),
    },
  ];

  const editingRole = editor?.type === 'edit' ? editor.role : null;
  const permRole = editor?.type === 'perms' ? editor.role : null;

  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '角色管理'}
        description={props.description ?? '查看系统角色，维护自定义角色与菜单按钮权限。'}
        extra={
          <Can permission={PERMISSION_CODE.tenantRoleCreate}>
            <Button type="primary" onClick={() => setEditor({ type: 'create' })}>
              新建角色
            </Button>
          </Can>
        }
      />
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={rolesQuery.isLoading}
          columns={columns}
          dataSource={rolesQuery.data}
          pagination={false}
        />
      </ListTableArea>

      <Modal
        title={editor?.type === 'create' ? '新建角色' : '编辑角色'}
        open={editor?.type === 'create' || editor?.type === 'edit'}
        onCancel={() => setEditor(null)}
        footer={null}
        destroyOnHidden
        width={720}
      >
        <Form
          layout="vertical"
          initialValues={
            editingRole
              ? {
                  name: editingRole.name,
                  code: editingRole.code,
                  description: editingRole.description,
                }
              : { permission_ids: [] }
          }
          onFinish={(values: {
            name: string;
            code?: string;
            description?: string;
            permission_ids?: number[];
          }) => {
            if (editor?.type === 'create') {
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
              });
            }
          }}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          {editor?.type === 'create' ? (
            <Form.Item name="code" label="编码" extra="创建后不可修改。" rules={[{ required: true, message: '请输入编码' }]}>
              <Input placeholder="如 DUTY" />
            </Form.Item>
          ) : (
            <Form.Item name="code" label="编码">
              <Input disabled />
            </Form.Item>
          )}
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={2} />
          </Form.Item>
          {editor?.type === 'create' ? (
            <Form.Item name="permission_ids" label="权限">
              <PermissionTree tree={treeQuery.data ?? []} />
            </Form.Item>
          ) : null}
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

      <Modal
        title={permRole ? `配置权限 · ${permRole.name}` : '配置权限'}
        open={editor?.type === 'perms'}
        onCancel={() => setEditor(null)}
        footer={null}
        destroyOnHidden
        width={720}
      >
        {permRole ? (
          <Form
            layout="vertical"
            initialValues={{ permission_ids: permRole.permissions.map((item) => item.id) }}
            onFinish={(values: { permission_ids: number[] }) =>
              permsMutation.mutate({
                roleId: permRole.id,
                permission_ids: [
                  ...new Set([
                    ...(values.permission_ids ?? []),
                    ...permRole.permissions.filter((item) => item.deprecated).map((item) => item.id),
                  ]),
                ],
              })
            }
          >
            {permRole.is_system ? (
              <p className="mb-3 text-sm text-slate-500">
                系统角色。可以调整业务权限，不能删除。勾选最终写入权限编码，不会保存目录节点。
              </p>
            ) : (
              <p className="mb-3 text-sm text-slate-500">按菜单与按钮勾选。父级目录本身不是权限。</p>
            )}
            <Form.Item name="permission_ids" label="权限">
              <PermissionTree tree={treeQuery.data ?? []} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={permsMutation.isPending} block>
              保存
            </Button>
          </Form>
        ) : null}
      </Modal>

      <Drawer title={viewing ? `角色详情 · ${viewing.name}` : '角色详情'} open={Boolean(viewing)} onClose={() => setViewing(null)} width={480}>
        {viewing ? (
          <div className="space-y-2 text-sm">
            <p>名称：{viewing.name}</p>
            <p>编码：{viewing.code}</p>
            <p>类型：{viewing.is_system ? '系统' : '自定义'}</p>
            <p>成员数：{viewing.member_count}</p>
            <p>说明：{viewing.description || '-'}</p>
            <p>权限：</p>
            <ul className="m-0 list-disc pl-5">
              {viewing.permissions
                .filter((item) => !item.deprecated)
                .map((item) => (
                  <li key={item.code}>
                    {item.name}（{item.code}）
                  </li>
                ))}
            </ul>
          </div>
        ) : null}
      </Drawer>
    </ListPageContainer>
  );
}
