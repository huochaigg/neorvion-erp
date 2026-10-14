import { DEFAULT_PAGE_SIZE, knowledgeApiKeysQueryKey, PERMISSION_CODE, type KnowledgeApiKey } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Drawer, Form, Input, Popconfirm, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { createApiKey, fetchApiKeys, revokeApiKey } from '@/api/ops';
import { ActionCell, AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';

export function ApiKeysPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [plaintext, setPlaintext] = useState<string | null>(null);
  const [form] = Form.useForm();
  const query = useQuery({
    queryKey: knowledgeApiKeysQueryKey(tenantId, { page, pageSize: DEFAULT_PAGE_SIZE }),
    queryFn: ({ signal }) => fetchApiKeys({ page, pageSize: DEFAULT_PAGE_SIZE }, signal),
    enabled: tenantId != null,
  });

  const create = useMutation({
    mutationFn: (values: { name: string; scopes: string[] }) => createApiKey(values),
    onSuccess: (row) => {
      setPlaintext(row.api_key ?? null);
      message.success('已创建，请立即保存明文密钥');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-api-keys'] });
    },
    onError: (error: Error) => message.error(error.message),
  });

  const columns: ColumnsType<KnowledgeApiKey> = [
    { title: '名称', dataIndex: 'name' },
    { title: '前缀', dataIndex: 'prefix', width: 140 },
    {
      title: '范围',
      dataIndex: 'scopes',
      render: (value: string[]) => value.map((item) => <Tag key={item}>{item}</Tag>),
    },
    {
      title: '状态',
      width: 100,
      render: (_, record) => (record.revoked_at ? <Tag color="red">已撤销</Tag> : <Tag color="green">有效</Tag>),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (value: string) => formatDateTime(value) },
    {
      title: '操作',
      width: 100,
      render: (_, record) =>
        record.revoked_at ? null : (
          <ActionCell>
            <Can permission={PERMISSION_CODE.knowledgeUpdate}>
              <Popconfirm
                title="撤销后立即失效"
                onConfirm={() =>
                  revokeApiKey(record.id)
                    .then(() => {
                      message.success('已撤销');
                      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'knowledge-api-keys'] });
                    })
                    .catch((error: Error) => message.error(error.message))
                }
              >
                <Button type="link" size="small" danger>
                  撤销
                </Button>
              </Popconfirm>
            </Can>
          </ActionCell>
        ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader
        title="API Key"
        description="给 Copilot / 客服 Agent 使用。明文只显示一次，服务端只存 SHA256。Key 不能改绑其他租户。"
        extra={
          <Can permission={PERMISSION_CODE.knowledgeUpdate}>
            <Button type="primary" onClick={() => setOpen(true)}>
              新建
            </Button>
          </Can>
        }
      />
      {plaintext ? (
        <Alert
          type="warning"
          showIcon
          className="mb-3"
          message="请立即复制明文密钥，关闭后无法再次查看"
          description={<code>{plaintext}</code>}
        />
      ) : null}
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total: query.data?.total ?? 0,
            onChange: setPage,
          }}
        />
      </ListTableArea>
      <Drawer title="新建 API Key" open={open} onClose={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={(values) => create.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="scopes" label="权限范围" initialValue={['search']} rules={[{ required: true }]}>
            <Select mode="multiple" options={[{ value: 'search' }, { value: 'chat' }, { value: 'stats' }]} />
          </Form.Item>
          <Space>
            <Button onClick={() => setOpen(false)}>取消</Button>
            <Button type="primary" htmlType="submit" loading={create.isPending}>
              创建
            </Button>
          </Space>
        </Form>
      </Drawer>
    </ListPageContainer>
  );
}
