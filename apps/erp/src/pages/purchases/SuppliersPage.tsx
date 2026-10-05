import {
  ApiError,
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  SUPPLIER_STATUS,
  supplierLocation,
  suppliersQueryKey,
  type Supplier,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, Popconfirm, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  changeSupplierStatus,
  createSupplier,
  deleteSupplier,
  fetchSuppliers,
  updateSupplier,
} from '@/api/suppliers';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

type EditorState =
  | { type: 'create' }
  | { type: 'edit'; supplier: Supplier }
  | { type: 'view'; supplier: Supplier };

interface SupplierFormValues {
  name: string;
  code?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
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

export function SuppliersPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [countryCode, setCountryCode] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);

  useEffect(() => {
    setEditor(null);
    setQ('');
    setKeyword('');
    setStatus(undefined);
    setCountryCode('');
    setPage(1);
  }, [tenantId]);

  const listQuery = useQuery({
    queryKey: suppliersQueryKey(tenantId, {
      q: keyword,
      status,
      countryCode: countryCode.trim() || undefined,
      page,
      pageSize,
    }),
    queryFn: ({ signal }) =>
      fetchSuppliers(
        {
          q: keyword,
          status,
          countryCode: countryCode.trim() || undefined,
          page,
          pageSize,
        },
        signal,
      ),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'suppliers'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'supplier'] });
  };

  const createMutation = useMutation({
    mutationFn: createSupplier,
    onSuccess: () => {
      message.success('供应商已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: { id: number } & SupplierFormValues) =>
      updateSupplier(values.id, {
        name: values.name,
        contact_name: emptyToNull(values.contact_name),
        contact_phone: emptyToNull(values.contact_phone),
        contact_email: emptyToNull(values.contact_email),
        country_code: emptyToNull(values.country_code)?.toUpperCase() ?? null,
        province: emptyToNull(values.province),
        city: emptyToNull(values.city),
        address: emptyToNull(values.address),
        remark: emptyToNull(values.remark),
      }),
    onSuccess: () => {
      message.success('供应商已更新');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, nextStatus }: { id: number; nextStatus: string }) =>
      changeSupplierStatus(id, nextStatus),
    onSuccess: (_, variables) => {
      message.success(variables.nextStatus === SUPPLIER_STATUS.active ? '供应商已启用' : '供应商已停用');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '状态更新失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSupplier,
    onSuccess: () => {
      message.success('供应商已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const columns: ColumnsType<Supplier> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '编码', dataIndex: 'code', key: 'code', width: 150 },
    {
      title: '联系人',
      dataIndex: 'contact_name',
      key: 'contact_name',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '电话',
      dataIndex: 'contact_phone',
      key: 'contact_phone',
      width: 130,
      render: (value: string | null) => value || '-',
    },
    {
      title: '国家 / 城市',
      key: 'location',
      width: 140,
      render: (_, record) => supplierLocation(record),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (value: string) => (
        <Tag color={value === SUPPLIER_STATUS.active ? 'success' : 'default'}>
          {value === SUPPLIER_STATUS.active ? '启用' : '停用'}
        </Tag>
      ),
    },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 180 },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_, record) => (
        <Space wrap>
          {hasPermission(PERMISSION_CODE.supplierUpdate) ? (
            <Button type="link" size="small" onClick={() => setEditor({ type: 'edit', supplier: record })}>
              编辑
            </Button>
          ) : (
            <Button type="link" size="small" onClick={() => setEditor({ type: 'view', supplier: record })}>
              查看
            </Button>
          )}
          <Can permission={PERMISSION_CODE.supplierDisable}>
            <Popconfirm
              title={
                record.status === SUPPLIER_STATUS.active
                  ? `确定停用「${record.name}」吗？停用后不能新建采购单。`
                  : `确定启用「${record.name}」吗？`
              }
              onConfirm={() =>
                statusMutation.mutate({
                  id: record.id,
                  nextStatus:
                    record.status === SUPPLIER_STATUS.active
                      ? SUPPLIER_STATUS.disabled
                      : SUPPLIER_STATUS.active,
                })
              }
            >
              <Button type="link" size="small">
                {record.status === SUPPLIER_STATUS.active ? '停用' : '启用'}
              </Button>
            </Popconfirm>
          </Can>
          <Can permission={PERMISSION_CODE.supplierDelete}>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => {
                modal.confirm({
                  title: '删除供应商',
                  content: '已被采购单引用的供应商不能删除，只能停用。',
                  onOk: () => deleteMutation.mutateAsync(record.id),
                });
              }}
            >
              删除
            </Button>
          </Can>
        </Space>
      ),
    },
  ];

  const readOnly = editor?.type === 'view';
  const editorTitle =
    editor?.type === 'edit' ? '编辑供应商' : editor?.type === 'view' ? '供应商详情' : '新增供应商';

  return (
    <div>
      <PageHeader
        title={props.title ?? '供应商管理'}
        description={props.description ?? '维护本企业供应商。停用后不能新建采购单，历史单据保留。'}
        extra={
          <Can permission={PERMISSION_CODE.supplierCreate}>
            <Button type="primary" onClick={() => setEditor({ type: 'create' })}>
              新增供应商
            </Button>
          </Can>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          className="w-56!"
          placeholder="名称 / 编码"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          onPressEnter={() => {
            setKeyword(q.trim());
            setPage(1);
          }}
          allowClear
        />
        <Select
          className="w-36"
          allowClear
          placeholder="状态"
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={[
            { value: SUPPLIER_STATUS.active, label: '启用' },
            { value: SUPPLIER_STATUS.disabled, label: '停用' },
          ]}
        />
        <Input
          className="w-56!"
          placeholder="国家代码"
          value={countryCode}
          onChange={(event) => setCountryCode(event.target.value.toUpperCase())}
          maxLength={2}
          allowClear
        />
        <Button
          onClick={() => {
            setKeyword(q.trim());
            setPage(1);
          }}
        >
          查询
        </Button>
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={listQuery.data?.items ?? []}
        loading={listQuery.isLoading}
        pagination={{
          current: page,
          pageSize,
          total: listQuery.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage);
            setPageSize(nextSize);
          },
        }}
      />
      <Drawer
        title={editorTitle}
        open={editor != null}
        onClose={() => setEditor(null)}
        width={480}
        destroyOnHidden
      >
        {editor ? (
          <Form
            layout="vertical"
            key={editor.type === 'create' ? 'create' : editor.supplier.id}
            initialValues={
              editor.type === 'create'
                ? { name: '', code: '' }
                : {
                    name: editor.supplier.name,
                    code: editor.supplier.code,
                    contact_name: editor.supplier.contact_name ?? '',
                    contact_phone: editor.supplier.contact_phone ?? '',
                    contact_email: editor.supplier.contact_email ?? '',
                    country_code: editor.supplier.country_code ?? '',
                    province: editor.supplier.province ?? '',
                    city: editor.supplier.city ?? '',
                    address: editor.supplier.address ?? '',
                    remark: editor.supplier.remark ?? '',
                  }
            }
            onFinish={(values: SupplierFormValues) => {
              if (editor.type === 'view') {
                return;
              }
              if (editor.type === 'create') {
                createMutation.mutate({
                  name: values.name,
                  code: emptyToNull(values.code),
                  contact_name: emptyToNull(values.contact_name),
                  contact_phone: emptyToNull(values.contact_phone),
                  contact_email: emptyToNull(values.contact_email),
                  country_code: emptyToNull(values.country_code)?.toUpperCase() ?? null,
                  province: emptyToNull(values.province),
                  city: emptyToNull(values.city),
                  address: emptyToNull(values.address),
                  remark: emptyToNull(values.remark),
                });
                return;
              }
              updateMutation.mutate({ id: editor.supplier.id, ...values });
            }}
          >
            <Form.Item name="name" label="供应商名称" rules={[{ required: true, message: '请输入供应商名称' }]}>
              <Input maxLength={128} disabled={readOnly} />
            </Form.Item>
            <Form.Item
              name="code"
              label="供应商编码"
              extra={
                editor.type === 'create'
                  ? '留空将由系统自动生成，例如 SUP0000000001'
                  : '供应商创建后编码不可修改'
              }
            >
              <Input maxLength={32} disabled={editor.type !== 'create'} />
            </Form.Item>
            <Form.Item name="contact_name" label="联系人">
              <Input maxLength={64} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="contact_phone" label="电话">
              <Input maxLength={32} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="contact_email" label="邮箱">
              <Input maxLength={128} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="country_code" label="国家" extra="ISO 两位代码，例如 CN">
              <Input maxLength={2} disabled={readOnly} placeholder="CN" />
            </Form.Item>
            <Form.Item name="province" label="省 / 州">
              <Input maxLength={64} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="city" label="城市">
              <Input maxLength={64} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="address" label="详细地址">
              <Input maxLength={255} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="remark" label="备注">
              <Input.TextArea rows={3} maxLength={255} disabled={readOnly} />
            </Form.Item>
            {readOnly ? null : (
              <Button
                type="primary"
                htmlType="submit"
                loading={createMutation.isPending || updateMutation.isPending}
              >
                保存
              </Button>
            )}
          </Form>
        ) : null}
      </Drawer>
    </div>
  );
}
