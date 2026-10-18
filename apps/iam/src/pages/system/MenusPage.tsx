import { PERMISSION_CODE } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal, Switch, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { fetchMenus, updateMenu, type IamMenu } from '@/api/catalog';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';

export function MenusPage(_props: PageProps) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<IamMenu | null>(null);
  const [form] = Form.useForm();
  const query = useQuery({
    queryKey: ['iam', 'menus'],
    queryFn: ({ signal }) => fetchMenus(signal),
  });
  const updateMutation = useMutation({
    mutationFn: (values: { id: number; title: string; path: string; visible: boolean; permission_code?: string }) =>
      updateMenu(values.id, {
        title: values.title,
        path: values.path,
        visible: values.visible,
        permission_code: values.permission_code || null,
      }),
    onSuccess: async () => {
      message.success('已更新菜单');
      setEditing(null);
      await queryClient.invalidateQueries({ queryKey: ['iam', 'menus'] });
    },
  });
  const columns: ColumnsType<IamMenu> = [
    { title: 'Key', dataIndex: 'menu_key', width: 220 },
    { title: '标题', dataIndex: 'title' },
    { title: '类型', dataIndex: 'menu_type', width: 100 },
    { title: '路径', dataIndex: 'path' },
    { title: '权限编码', dataIndex: 'permission_code', width: 220 },
    {
      title: '可见',
      dataIndex: 'visible',
      width: 80,
      render: (value: boolean) => (value ? <Tag color="success">是</Tag> : <Tag>否</Tag>),
    },
    {
      title: '锁定',
      dataIndex: 'locked',
      width: 80,
      render: (value: boolean) => (value ? '已锁定' : '未锁定'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_, row) => (
        <Can permission={PERMISSION_CODE.iamMenusManage}>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditing(row);
              form.setFieldsValue({
                title: row.title,
                path: row.path,
                visible: row.visible,
                permission_code: row.permission_code,
              });
            }}
          >
            编辑
          </Button>
        </Can>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title="菜单管理" description="菜单可见性不等于 API 授权。隐藏菜单不会放行或拒绝后端接口。" />
      <ListTableArea>
        <AppTable rowKey="id" loading={query.isLoading} columns={columns} dataSource={query.data ?? []} />
      </ListTableArea>
      <Modal
        title="编辑菜单"
        open={Boolean(editing)}
        onCancel={() => setEditing(null)}
        onOk={() => form.submit()}
        confirmLoading={updateMutation.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values: { title: string; path: string; visible: boolean; permission_code?: string }) => {
            if (!editing) {
              return;
            }
            updateMutation.mutate({ id: editing.id, ...values });
          }}
        >
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="path" label="路径">
            <Input />
          </Form.Item>
          <Form.Item name="permission_code" label="权限编码" extra="绑定功能权限；API 仍独立校验该编码。">
            <Input placeholder="order:read" />
          </Form.Item>
          <Form.Item name="visible" label="菜单可见" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageContainer>
  );
}
