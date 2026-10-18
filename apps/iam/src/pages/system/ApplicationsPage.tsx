import { PERMISSION_CODE } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { createApplication, fetchApplications, type IamApplication } from '@/api/catalog';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';

export function ApplicationsPage(_props: PageProps) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const query = useQuery({
    queryKey: ['iam', 'applications'],
    queryFn: ({ signal }) => fetchApplications(signal),
  });
  const createMutation = useMutation({
    mutationFn: createApplication,
    onSuccess: async () => {
      message.success('已注册应用');
      setOpen(false);
      form.resetFields();
      await queryClient.invalidateQueries({ queryKey: ['iam', 'applications'] });
    },
  });

  const columns: ColumnsType<IamApplication> = [
    { title: '编码', dataIndex: 'code', width: 160 },
    { title: '名称', dataIndex: 'name' },
    { title: 'Audience', dataIndex: 'audience', width: 200 },
    { title: '状态', dataIndex: 'status', width: 120 },
    { title: '说明', dataIndex: 'description' },
  ];

  return (
    <ListPageContainer>
      <PageHeader title="应用注册" description="后续 Copilot、客服等应用在此注册，不要硬编码仅 ERP 与 Knowledge。" />
      <ListToolbar>
        <Can permission={PERMISSION_CODE.iamAppsManage}>
          <Button type="primary" onClick={() => setOpen(true)}>
            注册应用
          </Button>
        </Can>
      </ListToolbar>
      <ListTableArea>
        <AppTable rowKey="id" loading={query.isLoading} columns={columns} dataSource={query.data ?? []} />
      </ListTableArea>
      <Modal
        title="注册应用"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(values) => createMutation.mutate(values)}>
          <Form.Item name="code" label="编码" rules={[{ required: true }]}>
            <Input placeholder="copilot" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="Neorvion Copilot" />
          </Form.Item>
          <Form.Item name="audience" label="JWT Audience" rules={[{ required: true }]}>
            <Input placeholder="neorvion-copilot" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageContainer>
  );
}
