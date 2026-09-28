import {
  ApiError,
  brandsQueryKey,
  CATALOG_STATUS,
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  type Brand,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, Modal, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { createBrand, deleteBrand, fetchBrands, updateBrand } from '@/api/catalog';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

type EditorState = { type: 'create' } | { type: 'edit'; brand: Brand };

export function BrandsPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);

  useEffect(() => {
    setEditor(null);
    setQ('');
    setKeyword('');
    setStatus(undefined);
    setPage(1);
  }, [tenantId]);

  const brandsQuery = useQuery({
    queryKey: brandsQueryKey(tenantId, { q: keyword, status, page, pageSize }),
    queryFn: ({ signal }) => fetchBrands({ q: keyword, status, page, pageSize }, signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'brands'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'brand-options'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'products'] });
  };

  const createMutation = useMutation({
    mutationFn: createBrand,
    onSuccess: () => {
      message.success('品牌已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: {
      id: number;
      name?: string;
      logo_url?: string | null;
      description?: string | null;
      status?: string;
    }) =>
      updateBrand(values.id, {
        name: values.name,
        logo_url: values.logo_url,
        description: values.description,
        status: values.status,
      }),
    onSuccess: () => {
      message.success('品牌已更新');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBrand,
    onSuccess: () => {
      message.success('品牌已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const columns: ColumnsType<Brand> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '编码', dataIndex: 'code', key: 'code', width: 140 },
    {
      title: 'Logo',
      dataIndex: 'logo_url',
      key: 'logo_url',
      ellipsis: true,
      render: (url: string | null) => url || '-',
    },
    {
      title: '说明',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (text: string | null) => text || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === CATALOG_STATUS.active ? 'success' : 'default'}>
          {value === CATALOG_STATUS.active ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Can permission={PERMISSION_CODE.productUpdate}>
            <Button type="link" size="small" onClick={() => setEditor({ type: 'edit', brand: record })}>
              编辑
            </Button>
            <Button
              type="link"
              size="small"
              onClick={() =>
                updateMutation.mutate({
                  id: record.id,
                  status:
                    record.status === CATALOG_STATUS.active
                      ? CATALOG_STATUS.disabled
                      : CATALOG_STATUS.active,
                })
              }
            >
              {record.status === CATALOG_STATUS.active ? '停用' : '启用'}
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.productDelete}>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => {
                modal.confirm({
                  title: '删除品牌',
                  content: '已被商品使用的品牌不能删除。',
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

  return (
    <div>
      <PageHeader
        title={props.title ?? '品牌管理'}
        description={props.description ?? '每个企业维护自己的品牌。编码在租户内唯一。Logo 先填 URL。'}
        extra={
          <Can permission={PERMISSION_CODE.productUpdate}>
            <Button type="primary" onClick={() => setEditor({ type: 'create' })}>
              新增品牌
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
          placeholder="状态"
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={[
            { value: CATALOG_STATUS.active, label: '启用' },
            { value: CATALOG_STATUS.disabled, label: '停用' },
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
        dataSource={brandsQuery.data?.items ?? []}
        loading={brandsQuery.isLoading}
        pagination={{
          current: page,
          pageSize,
          total: brandsQuery.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage);
            setPageSize(nextSize);
          },
        }}
      />
      <Modal
        title={editor?.type === 'edit' ? '编辑品牌' : '新增品牌'}
        open={editor != null}
        onCancel={() => setEditor(null)}
        footer={null}
        destroyOnHidden
      >
        {editor ? (
          <Form
            layout="vertical"
            key={editor.type === 'edit' ? editor.brand.id : 'create'}
            initialValues={
              editor.type === 'edit'
                ? {
                    name: editor.brand.name,
                    code: editor.brand.code,
                    logo_url: editor.brand.logo_url ?? '',
                    description: editor.brand.description ?? '',
                  }
                : { name: '', code: '', logo_url: '', description: '' }
            }
            onFinish={(values: {
              name: string;
              code: string;
              logo_url?: string;
              description?: string;
            }) => {
              if (editor.type === 'create') {
                createMutation.mutate({
                  name: values.name,
                  code: values.code,
                  logo_url: values.logo_url || null,
                  description: values.description || null,
                });
                return;
              }
              updateMutation.mutate({
                id: editor.brand.id,
                name: values.name,
                logo_url: values.logo_url || null,
                description: values.description || null,
              });
            }}
          >
            <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
              <Input maxLength={64} />
            </Form.Item>
            <Form.Item
              name="code"
              label="编码"
              rules={[{ required: true, message: '请输入编码' }]}
              extra="字母开头，租户内唯一。创建后不可改。"
            >
              <Input maxLength={32} disabled={editor.type === 'edit'} />
            </Form.Item>
            <Form.Item name="logo_url" label="Logo URL">
              <Input maxLength={255} />
            </Form.Item>
            <Form.Item name="description" label="说明">
              <Input.TextArea rows={3} maxLength={255} />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={createMutation.isPending || updateMutation.isPending}
            >
              保存
            </Button>
          </Form>
        ) : null}
      </Modal>
    </div>
  );
}
