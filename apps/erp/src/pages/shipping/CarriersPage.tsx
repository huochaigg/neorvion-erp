import {
  ApiError,
  CARRIER_STATUS,
  CARRIER_TYPE_OPTIONS,
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  carrierTypeLabel,
  carriersQueryKey,
  type Carrier,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Drawer, Form, Input, Popconfirm, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  changeCarrierStatus,
  createCarrier,
  deleteCarrier,
  fetchCarriers,
  updateCarrier,
} from '@/api/carriers';
import { ActionCell, AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

type EditorState =
  | { type: 'create' }
  | { type: 'edit'; carrier: Carrier }
  | { type: 'view'; carrier: Carrier };

interface CarrierFormValues {
  name: string;
  code?: string;
  carrier_type: string;
  contact_name?: string;
  contact_phone?: string;
  website?: string;
  remark?: string;
}

function emptyToNull(value?: string) {
  const text = value?.trim();
  return text ? text : null;
}

export function CarriersPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [carrierType, setCarrierType] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);

  useEffect(() => {
    setEditor(null);
    setQ('');
    setKeyword('');
    setStatus(undefined);
    setCarrierType(undefined);
    setPage(1);
  }, [tenantId]);

  const listQuery = useQuery({
    queryKey: carriersQueryKey(tenantId, {
      q: keyword,
      status,
      carrierType,
      page,
      pageSize,
    }),
    queryFn: ({ signal }) =>
      fetchCarriers(
        { q: keyword, status, carrierType, page, pageSize },
        signal,
      ),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'carriers'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'carrier'] });
  };

  const createMutation = useMutation({
    mutationFn: createCarrier,
    onSuccess: () => {
      message.success('物流商已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: { id: number } & CarrierFormValues) =>
      updateCarrier(values.id, {
        name: values.name,
        carrier_type: values.carrier_type,
        contact_name: emptyToNull(values.contact_name),
        contact_phone: emptyToNull(values.contact_phone),
        website: emptyToNull(values.website),
        remark: emptyToNull(values.remark),
      }),
    onSuccess: () => {
      message.success('物流商已更新');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, nextStatus }: { id: number; nextStatus: string }) =>
      changeCarrierStatus(id, nextStatus),
    onSuccess: (_, variables) => {
      message.success(variables.nextStatus === CARRIER_STATUS.active ? '物流商已启用' : '物流商已停用');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '状态更新失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCarrier,
    onSuccess: () => {
      message.success('物流商已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const columns: ColumnsType<Carrier> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 180,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '编码',
      dataIndex: 'code',
      width: 160,
      render: (value: string) => <CodeCell value={value} />,
    },
    {
      title: '类型',
      dataIndex: 'carrier_type',
      width: 140,
      render: (value: string) => carrierTypeLabel(value),
    },
    {
      title: '联系人',
      dataIndex: 'contact_name',
      width: 120,
      render: (value: string | null) => <EllipsisCell value={value || '-'} />,
    },
    {
      title: '联系电话',
      dataIndex: 'contact_phone',
      width: 140,
      render: (value: string | null) => <CodeCell value={value || '-'} />,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => (
        <Tag color={value === CARRIER_STATUS.active ? 'success' : 'default'}>
          {value === CARRIER_STATUS.active ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        <ActionCell>
          {hasPermission(PERMISSION_CODE.carrierUpdate) ? (
            <Button type="link" size="small" onClick={() => setEditor({ type: 'edit', carrier: record })}>
              编辑
            </Button>
          ) : (
            <Button type="link" size="small" onClick={() => setEditor({ type: 'view', carrier: record })}>
              查看
            </Button>
          )}
          <Can permission={PERMISSION_CODE.carrierDisable}>
            <Popconfirm
              title={
                record.status === CARRIER_STATUS.active
                  ? `确定停用「${record.name}」吗？停用后不能新建物流单。`
                  : `确定启用「${record.name}」吗？`
              }
              onConfirm={() =>
                statusMutation.mutate({
                  id: record.id,
                  nextStatus:
                    record.status === CARRIER_STATUS.active
                      ? CARRIER_STATUS.disabled
                      : CARRIER_STATUS.active,
                })
              }
            >
              <Button type="link" size="small">
                {record.status === CARRIER_STATUS.active ? '停用' : '启用'}
              </Button>
            </Popconfirm>
          </Can>
          <Can permission={PERMISSION_CODE.carrierDelete}>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => {
                modal.confirm({
                  title: '删除物流商',
                  content: '已被物流单引用的物流商不能删除，只能停用。',
                  onOk: () => deleteMutation.mutateAsync(record.id),
                });
              }}
            >
              删除
            </Button>
          </Can>
        </ActionCell>
      ),
    },
  ];

  const readOnly = editor?.type === 'view';
  const editorTitle =
    editor?.type === 'edit' ? '编辑物流商' : editor?.type === 'view' ? '物流商详情' : '新增物流商';

  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '物流商'}
        description={props.description ?? '维护承运商档案。不调用真实物流 API。'}
        extra={
          <Can permission={PERMISSION_CODE.carrierCreate}>
            <Button type="primary" onClick={() => setEditor({ type: 'create' })}>
              新增物流商
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
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
            className="w-40"
            allowClear
            placeholder="类型"
            value={carrierType}
            onChange={(value) => {
              setCarrierType(value);
              setPage(1);
            }}
            options={CARRIER_TYPE_OPTIONS}
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
              { value: CARRIER_STATUS.active, label: '启用' },
              { value: CARRIER_STATUS.disabled, label: '停用' },
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
        title={editorTitle}
        open={editor != null}
        onClose={() => setEditor(null)}
        width={480}
        destroyOnHidden
      >
        {editor ? (
          <Form
            layout="vertical"
            key={editor.type === 'create' ? 'create' : editor.carrier.id}
            initialValues={
              editor.type === 'create'
                ? { name: '', code: '', carrier_type: 'DOMESTIC_EXPRESS' }
                : {
                    name: editor.carrier.name,
                    code: editor.carrier.code,
                    carrier_type: editor.carrier.carrier_type,
                    contact_name: editor.carrier.contact_name ?? '',
                    contact_phone: editor.carrier.contact_phone ?? '',
                    website: editor.carrier.website ?? '',
                    remark: editor.carrier.remark ?? '',
                  }
            }
            onFinish={(values: CarrierFormValues) => {
              if (editor.type === 'view') {
                return;
              }
              if (editor.type === 'create') {
                createMutation.mutate({
                  name: values.name,
                  code: emptyToNull(values.code),
                  carrier_type: values.carrier_type,
                  contact_name: emptyToNull(values.contact_name),
                  contact_phone: emptyToNull(values.contact_phone),
                  website: emptyToNull(values.website),
                  remark: emptyToNull(values.remark),
                });
                return;
              }
              updateMutation.mutate({ id: editor.carrier.id, ...values });
            }}
          >
            <Form.Item name="name" label="物流商名称" rules={[{ required: true, message: '请输入名称' }]}>
              <Input maxLength={128} disabled={readOnly} />
            </Form.Item>
            <Form.Item
              name="code"
              label="物流商编码"
              extra={
                editor.type === 'create'
                  ? '留空将由系统自动生成，例如 CAR0000000001'
                  : '物流商创建后编码不可修改'
              }
            >
              <Input maxLength={32} disabled={editor.type !== 'create'} />
            </Form.Item>
            <Form.Item name="carrier_type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
              <Select options={CARRIER_TYPE_OPTIONS} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="contact_name" label="联系人">
              <Input maxLength={64} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="contact_phone" label="联系电话">
              <Input maxLength={32} disabled={readOnly} />
            </Form.Item>
            <Form.Item name="website" label="网站">
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
    </ListPageContainer>
  );
}
