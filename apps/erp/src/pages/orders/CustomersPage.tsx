import {
  ApiError,
  CUSTOMER_STATUS,
  customerLocation,
  customersQueryKey,
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  type Customer,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, Popconfirm, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  changeCustomerStatus,
  createCustomer,
  deleteCustomer,
  fetchCustomers,
  updateCustomer,
} from '@/api/customers';
import { ActionCell, AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

type EditorState = { type: 'create' } | { type: 'edit'; customer: Customer } | { type: 'view'; customer: Customer };

interface CustomerFormValues {
  name: string;
  code?: string;
  email?: string;
  phone?: string;
  country_code?: string;
  province?: string;
  city?: string;
  address?: string;
  remark?: string;
}

function emptyToNull(value?: string) {
  const text = value?.trim();
  return text ? text : null;
}

export function CustomersPage(props: PageProps) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [form] = Form.useForm<CustomerFormValues>();

  useEffect(() => {
    setEditor(null);
    setQ('');
    setKeyword('');
    setStatus(undefined);
    setPage(1);
  }, [tenantId]);

  const listQuery = useQuery({
    queryKey: customersQueryKey(tenantId, { q: keyword, status, page, pageSize }),
    queryFn: ({ signal }) => fetchCustomers({ q: keyword, status, page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'customers'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'customer'] });
  };

  const saveMutation = useMutation({
    mutationFn: async (values: CustomerFormValues) => {
      if (editor?.type === 'edit') {
        return updateCustomer(editor.customer.id, {
          name: values.name.trim(),
          email: emptyToNull(values.email),
          phone: emptyToNull(values.phone),
          country_code: emptyToNull(values.country_code)?.toUpperCase() ?? null,
          province: emptyToNull(values.province),
          city: emptyToNull(values.city),
          address: emptyToNull(values.address),
          remark: emptyToNull(values.remark),
        });
      }
      return createCustomer({
        name: values.name.trim(),
        code: emptyToNull(values.code),
        email: emptyToNull(values.email),
        phone: emptyToNull(values.phone),
        country_code: emptyToNull(values.country_code)?.toUpperCase() ?? null,
        province: emptyToNull(values.province),
        city: emptyToNull(values.city),
        address: emptyToNull(values.address),
        remark: emptyToNull(values.remark),
      });
    },
    onSuccess: () => {
      message.success(editor?.type === 'edit' ? '客户已保存' : '客户已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, next }: { id: number; next: string }) => changeCustomerStatus(id, next),
    onSuccess: () => {
      message.success('状态已更新');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '状态更新失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCustomer,
    onSuccess: () => {
      message.success('已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const openEditor = (next: EditorState) => {
    setEditor(next);
    if (next.type === 'create') {
      form.resetFields();
      return;
    }
    form.setFieldsValue({
      name: next.customer.name,
      code: next.customer.code,
      email: next.customer.email ?? '',
      phone: next.customer.phone ?? '',
      country_code: next.customer.country_code ?? '',
      province: next.customer.province ?? '',
      city: next.customer.city ?? '',
      address: next.customer.address ?? '',
      remark: next.customer.remark ?? '',
    });
  };

  const columns: ColumnsType<Customer> = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 180, render: (value: string) => <EllipsisCell value={value} /> },
    { title: '编码', dataIndex: 'code', key: 'code', width: 160, render: (value: string) => <CodeCell value={value} /> },
    { title: 'Email', dataIndex: 'email', key: 'email', width: 200, render: (value: string | null) => <EllipsisCell value={value} /> },
    { title: '电话', dataIndex: 'phone', key: 'phone', width: 140, render: (value: string | null) => <EllipsisCell value={value} /> },
    {
      title: '国家 / 城市',
      key: 'location',
      width: 140,
      render: (_, record) => <EllipsisCell value={customerLocation(record)} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === CUSTOMER_STATUS.active ? 'success' : 'default'}>
          {value === CUSTOMER_STATUS.active ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => openEditor({ type: 'view', customer: record })}>
            查看
          </Button>
          <Can permission={PERMISSION_CODE.customerUpdate}>
            <Button type="link" size="small" onClick={() => openEditor({ type: 'edit', customer: record })}>
              编辑
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.customerDisable}>
            <Button
              type="link"
              size="small"
              onClick={() =>
                statusMutation.mutate({
                  id: record.id,
                  next: record.status === CUSTOMER_STATUS.active ? CUSTOMER_STATUS.disabled : CUSTOMER_STATUS.active,
                })
              }
            >
              {record.status === CUSTOMER_STATUS.active ? '停用' : '启用'}
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.customerDelete}>
            <Popconfirm title="删除这个客户？" onConfirm={() => deleteMutation.mutate(record.id)}>
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </Can>
        </ActionCell>
      ),
    },
  ];

  const readonly = editor?.type === 'view';

  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '客户管理'}
        description={props.description ?? '停用后不能新建订单。已被订单使用的客户不能删除。'}
        extra={
          <Can permission={PERMISSION_CODE.customerCreate}>
            <Button type="primary" onClick={() => openEditor({ type: 'create' })}>
              新增客户
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="名称 / 编码 / 邮箱 / 电话"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onSearch={(value) => {
              setKeyword(value.trim());
              setPage(1);
            }}
            style={{ width: 260 }}
          />
          <Select
            allowClear
            placeholder="状态"
            value={status}
            style={{ width: 120 }}
            options={[
              { value: CUSTOMER_STATUS.active, label: '启用' },
              { value: CUSTOMER_STATUS.disabled, label: '停用' },
            ]}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
          />
        </div>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          loading={listQuery.isLoading}
          pagination={{
            current: page,
            pageSize,
            total: listQuery.data?.total ?? 0,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </ListTableArea>
      <Drawer
        title={editor?.type === 'edit' ? '编辑客户' : editor?.type === 'view' ? '客户详情' : '新增客户'}
        open={editor != null}
        width={480}
        destroyOnClose
        onClose={() => setEditor(null)}
        extra={
          readonly ? null : (
            <Button type="primary" loading={saveMutation.isPending} onClick={() => form.submit()}>
              保存
            </Button>
          )
        }
      >
        <Form form={form} layout="vertical" disabled={readonly} onFinish={(values) => saveMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写客户名称' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="code" label="编码" extra={editor?.type === 'create' ? '留空则自动生成 CUS + 10 位 id' : '创建后不可修改'}>
            <Input maxLength={32} disabled={editor?.type !== 'create'} />
          </Form.Item>
          <Form.Item name="email" label="Email">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input maxLength={32} />
          </Form.Item>
          <Form.Item name="country_code" label="国家">
            <Input maxLength={2} placeholder="CN" />
          </Form.Item>
          <Form.Item name="province" label="省 / 州">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="city" label="城市">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="address" label="详细地址">
            <Input.TextArea rows={2} maxLength={255} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} maxLength={255} />
          </Form.Item>
        </Form>
      </Drawer>
    </ListPageContainer>
  );
}
