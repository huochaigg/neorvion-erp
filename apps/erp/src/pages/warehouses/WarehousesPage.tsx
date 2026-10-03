import {
  ApiError,
  canSetWarehouseDefault,
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  WAREHOUSE_STATUS,
  WAREHOUSE_TYPE,
  WAREHOUSE_TYPE_OPTIONS,
  warehouseLocation,
  warehousesQueryKey,
  warehouseTypeLabel,
  type Warehouse,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  changeWarehouseStatus,
  createWarehouse,
  deleteWarehouse,
  fetchWarehouses,
  setDefaultWarehouse,
  updateWarehouse,
} from '@/api/warehouses';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

type EditorState =
  | { type: 'create' }
  | { type: 'edit'; warehouse: Warehouse }
  | { type: 'view'; warehouse: Warehouse };

interface WarehouseFormValues {
  name: string;
  code?: string;
  type: string;
  country_code?: string;
  province?: string;
  city?: string;
  address?: string;
  contact_name?: string;
  contact_phone?: string;
  remark?: string;
}

function emptyToNull(value?: string) {
  const text = value?.trim();
  return text ? text : null;
}

export function WarehousesPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [warehouseType, setWarehouseType] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);

  useEffect(() => {
    setEditor(null);
    setQ('');
    setKeyword('');
    setWarehouseType(undefined);
    setStatus(undefined);
    setPage(1);
  }, [tenantId]);

  const listQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, {
      q: keyword,
      type: warehouseType,
      status,
      page,
      pageSize,
    }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ q: keyword, type: warehouseType, status, page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'warehouses'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'warehouse'] });
  };

  const createMutation = useMutation({
    mutationFn: createWarehouse,
    onSuccess: () => {
      message.success('仓库已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: { id: number } & WarehouseFormValues) =>
      updateWarehouse(values.id, {
        name: values.name,
        type: values.type,
        country_code: emptyToNull(values.country_code)?.toUpperCase() ?? null,
        province: emptyToNull(values.province),
        city: emptyToNull(values.city),
        address: emptyToNull(values.address),
        contact_name: emptyToNull(values.contact_name),
        contact_phone: emptyToNull(values.contact_phone),
        remark: emptyToNull(values.remark),
      }),
    onSuccess: () => {
      message.success('仓库已更新');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, nextStatus }: { id: number; nextStatus: string }) =>
      changeWarehouseStatus(id, nextStatus),
    onSuccess: (_, variables) => {
      message.success(variables.nextStatus === WAREHOUSE_STATUS.active ? '仓库已启用' : '仓库已停用');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '状态更新失败');
    },
  });

  const defaultMutation = useMutation({
    mutationFn: setDefaultWarehouse,
    onSuccess: () => {
      message.success('已设为默认仓库');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '设置失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteWarehouse,
    onSuccess: () => {
      message.success('仓库已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const columns: ColumnsType<Warehouse> = [
    { title: '仓库名称', dataIndex: 'name', key: 'name' },
    { title: '仓库编码', dataIndex: 'code', key: 'code', width: 140 },
    {
      title: '仓库类型',
      dataIndex: 'type',
      key: 'type',
      width: 120,
      render: (value: string) => warehouseTypeLabel(value),
    },
    {
      title: '国家 / 城市',
      key: 'location',
      width: 140,
      render: (_, record) => warehouseLocation(record),
    },
    {
      title: '默认仓库',
      dataIndex: 'is_default',
      key: 'is_default',
      width: 100,
      render: (value: boolean) => (value ? <Tag color="blue">默认</Tag> : '-'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (value: string) => (
        <Tag color={value === WAREHOUSE_STATUS.active ? 'success' : 'default'}>
          {value === WAREHOUSE_STATUS.active ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '联系人',
      dataIndex: 'contact_name',
      key: 'contact_name',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      render: (_, record) => (
        <Space wrap>
          {hasPermission(PERMISSION_CODE.warehouseUpdate) ? (
            <Button type="link" size="small" onClick={() => setEditor({ type: 'edit', warehouse: record })}>
              编辑
            </Button>
          ) : (
            <Button type="link" size="small" onClick={() => setEditor({ type: 'view', warehouse: record })}>
              查看
            </Button>
          )}
          {canSetWarehouseDefault(record) ? (
            <Can permission={PERMISSION_CODE.warehouseUpdate}>
              <Popconfirm
                title={`确定将「${record.name}」设为默认仓库吗？`}
                onConfirm={() => defaultMutation.mutate(record.id)}
              >
                <Button type="link" size="small">
                  设为默认
                </Button>
              </Popconfirm>
            </Can>
          ) : null}
          <Can permission={PERMISSION_CODE.warehouseDisable}>
            <Popconfirm
              title={
                record.status === WAREHOUSE_STATUS.active
                  ? `确定停用「${record.name}」吗？`
                  : `确定启用「${record.name}」吗？`
              }
              onConfirm={() =>
                statusMutation.mutate({
                  id: record.id,
                  nextStatus:
                    record.status === WAREHOUSE_STATUS.active
                      ? WAREHOUSE_STATUS.disabled
                      : WAREHOUSE_STATUS.active,
                })
              }
            >
              <Button type="link" size="small">
                {record.status === WAREHOUSE_STATUS.active ? '停用' : '启用'}
              </Button>
            </Popconfirm>
          </Can>
          <Can permission={PERMISSION_CODE.warehouseDelete}>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => {
                modal.confirm({
                  title: '删除仓库',
                  content: '删除后不可恢复。若该仓库是默认仓库且不是最后一个，请先切换默认仓库。',
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
    editor?.type === 'edit' ? '编辑仓库' : editor?.type === 'view' ? '仓库详情' : '新增仓库';

  return (
    <div>
      <PageHeader
        title={props.title ?? '仓库管理'}
        description={
          props.description ??
          '维护本企业仓库档案。后续库存按仓库 + SKU 记账，本页不显示库存数量。'
        }
        extra={
          <Can permission={PERMISSION_CODE.warehouseCreate}>
            <Button type="primary" onClick={() => setEditor({ type: 'create' })}>
              新增仓库
            </Button>
          </Can>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          className="w-56"
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
          placeholder="类型"
          value={warehouseType}
          onChange={(value) => {
            setWarehouseType(value);
            setPage(1);
          }}
          options={WAREHOUSE_TYPE_OPTIONS}
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
            { value: WAREHOUSE_STATUS.active, label: '启用' },
            { value: WAREHOUSE_STATUS.disabled, label: '停用' },
          ]}
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
            key={editor.type === 'create' ? 'create' : editor.warehouse.id}
            initialValues={
              editor.type === 'create'
                ? { name: '', code: '', type: WAREHOUSE_TYPE.domestic }
                : {
                    name: editor.warehouse.name,
                    code: editor.warehouse.code,
                    type: editor.warehouse.type,
                    country_code: editor.warehouse.country_code ?? '',
                    province: editor.warehouse.province ?? '',
                    city: editor.warehouse.city ?? '',
                    address: editor.warehouse.address ?? '',
                    contact_name: editor.warehouse.contact_name ?? '',
                    contact_phone: editor.warehouse.contact_phone ?? '',
                    remark: editor.warehouse.remark ?? '',
                  }
            }
            onFinish={(values: WarehouseFormValues) => {
              if (editor.type === 'view') {
                return;
              }
              if (editor.type === 'create') {
                createMutation.mutate({
                  name: values.name,
                  code: emptyToNull(values.code),
                  type: values.type,
                  country_code: emptyToNull(values.country_code)?.toUpperCase() ?? null,
                  province: emptyToNull(values.province),
                  city: emptyToNull(values.city),
                  address: emptyToNull(values.address),
                  contact_name: emptyToNull(values.contact_name),
                  contact_phone: emptyToNull(values.contact_phone),
                  remark: emptyToNull(values.remark),
                });
                return;
              }
              updateMutation.mutate({ id: editor.warehouse.id, ...values });
            }}
          >
            <Form.Item name="name" label="仓库名称" rules={[{ required: true, message: '请输入仓库名称' }]}>
              <Input maxLength={64} disabled={readOnly} />
            </Form.Item>
            <Form.Item
              name="code"
              label="仓库编码"
              extra={
                editor.type === 'create'
                  ? '留空将由系统自动生成，例如 WH0000000001'
                  : '仓库创建后编码不可修改'
              }
            >
              <Input maxLength={32} disabled={editor.type !== 'create'} />
            </Form.Item>
            <Form.Item name="type" label="仓库类型" rules={[{ required: true, message: '请选择仓库类型' }]}>
              <Select options={WAREHOUSE_TYPE_OPTIONS} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="country_code" label="国家" extra="ISO 两位代码，例如 CN、US、SG">
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
            <Form.Item name="contact_name" label="联系人">
              <Input maxLength={64} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="contact_phone" label="联系电话">
              <Input maxLength={32} disabled={readOnly} />
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
