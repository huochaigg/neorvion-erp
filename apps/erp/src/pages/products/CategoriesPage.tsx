import {
  ApiError,
  CATALOG_STATUS,
  categoryRowExpandable,
  PERMISSION_CODE,
  productCategoriesQueryKey,
  toCategoryTableRows,
  type CategoryTableRow,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, InputNumber, Modal, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { MouseEvent } from 'react';
import { useEffect, useState } from 'react';
import {
  createProductCategory,
  deleteProductCategory,
  fetchProductCategories,
  updateProductCategory,
} from '@/api/catalog';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

type EditorState =
  | { type: 'create'; parent?: CategoryTableRow }
  | { type: 'edit'; category: CategoryTableRow };

export function CategoriesPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [editor, setEditor] = useState<EditorState | null>(null);

  useEffect(() => {
    setEditor(null);
  }, [tenantId]);

  const treeQuery = useQuery({
    queryKey: productCategoriesQueryKey(tenantId),
    queryFn: ({ signal }) => fetchProductCategories(signal),
    enabled: tenantId != null,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: productCategoriesQueryKey(tenantId) });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'products'] });
  };

  const createMutation = useMutation({
    mutationFn: createProductCategory,
    onSuccess: () => {
      message.success('类目已创建');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '创建失败');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: { id: number; name?: string; sort?: number; status?: string }) =>
      updateProductCategory(values.id, {
        name: values.name,
        sort: values.sort,
        status: values.status,
      }),
    onSuccess: () => {
      message.success('类目已更新');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteProductCategory,
    onSuccess: () => {
      message.success('类目已删除');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '删除失败');
    },
  });

  const columns: ColumnsType<CategoryTableRow> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '层级', dataIndex: 'level', key: 'level', width: 80 },
    { title: '排序', dataIndex: 'sort', key: 'sort', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === CATALOG_STATUS.active ? 'success' : 'default'}>
          {status === CATALOG_STATUS.active ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      render: (_, record) => (
        <Space wrap>
          <Can permission={PERMISSION_CODE.productUpdate}>
            {record.level < 3 ? (
              <Button
                type="link"
                size="small"
                onClick={() => setEditor({ type: 'create', parent: record })}
              >
                新增子类目
              </Button>
            ) : null}
            <Button type="link" size="small" onClick={() => setEditor({ type: 'edit', category: record })}>
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
                  title: '删除类目',
                  content: '服务端会检查子类目和商品引用。有子节点或已被商品使用时不能删除。',
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
        title={props.title ?? '类目管理'}
        description={props.description ?? '最多三级。删除前由服务端校验子类目和商品引用。'}
        extra={
          <Can permission={PERMISSION_CODE.productUpdate}>
            <Button type="primary" onClick={() => setEditor({ type: 'create' })}>
              新增根类目
            </Button>
          </Can>
        }
      />
      <Table
        rowKey="id"
        columns={columns}
        dataSource={toCategoryTableRows(treeQuery.data ?? [])}
        loading={treeQuery.isLoading}
        pagination={false}
        scroll={{ y: 'calc(100vh - 280px)' }}
        expandable={{
          childrenColumnName: 'children',
          rowExpandable: (record) => categoryRowExpandable(record),
          expandIconColumnIndex: 0,
          expandIcon: ({ expandable, expanded, onExpand, record }) => {
            if (!expandable) {
              return null;
            }
            return (
              <button
                type="button"
                className={
                  expanded
                    ? 'ant-table-row-expand-icon ant-table-row-expand-icon-expanded'
                    : 'ant-table-row-expand-icon ant-table-row-expand-icon-collapsed'
                }
                aria-label={expanded ? '收起' : '展开'}
                onClick={(event: MouseEvent<HTMLElement>) => onExpand(record, event)}
              />
            );
          },
        }}
      />
      <Modal
        title={
          editor?.type === 'edit'
            ? '编辑类目'
            : editor?.parent
              ? `新增子类目（${editor.parent.name}）`
              : '新增根类目'
        }
        open={editor != null}
        onCancel={() => setEditor(null)}
        footer={null}
        destroyOnHidden
      >
        {editor ? (
          <Form
            layout="vertical"
            key={`${editor.type}-${editor.type === 'edit' ? editor.category.id : editor.parent?.id ?? 'root'}`}
            initialValues={
              editor.type === 'edit'
                ? { name: editor.category.name, sort: editor.category.sort }
                : { name: '', sort: 0 }
            }
            onFinish={(values: { name: string; sort: number }) => {
              if (editor.type === 'create') {
                createMutation.mutate({
                  name: values.name,
                  parent_id: editor.parent?.id,
                  sort: values.sort,
                });
                return;
              }
              updateMutation.mutate({
                id: editor.category.id,
                name: values.name,
                sort: values.sort,
              });
            }}
          >
            <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
              <Input maxLength={64} />
            </Form.Item>
            <Form.Item name="sort" label="排序" rules={[{ required: true }]}>
              <InputNumber min={0} max={9999} className="w-full" />
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
