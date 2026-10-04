import {
  ApiError,
  brandOptionsQueryKey,
  canAdjustOut,
  DEFAULT_PAGE_SIZE,
  INVENTORY_STOCK_STATUS,
  INVENTORY_TRANSACTION_TYPE,
  inventoryQueryKey,
  inventoryStockStatus,
  PERMISSION_CODE,
  productCategoriesQueryKey,
  productSkuOptionsQueryKey,
  specValuesLabel,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type InventoryItem,
  type ProductCategory,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  TreeSelect,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchBrandOptions, fetchProductCategories } from '@/api/catalog';
import {
  adjustInventory,
  fetchInventory,
  fetchSkuOptions,
  initializeInventory,
} from '@/api/inventory';
import { fetchWarehouses } from '@/api/warehouses';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

type EditorState =
  | { type: 'initialize' }
  | { type: 'adjust'; inventory: InventoryItem };

interface CategoryTreeNode {
  value: number;
  title: string;
  children?: CategoryTreeNode[];
}

function toTreeData(nodes: ProductCategory[]): CategoryTreeNode[] {
  return nodes.map((node) => ({
    value: node.id,
    title: node.name,
    children: node.children.length ? toTreeData(node.children) : undefined,
  }));
}

function stockTag(item: InventoryItem, threshold: number) {
  const status = inventoryStockStatus({ ...item, threshold });
  if (status === INVENTORY_STOCK_STATUS.zero) {
    return <Tag>零库存</Tag>;
  }
  if (status === INVENTORY_STOCK_STATUS.low) {
    return <Tag color="warning">低库存</Tag>;
  }
  return <Tag color="success">有库存</Tag>;
}

export function InventoryListPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [skuCode, setSkuCode] = useState('');
  const [keyword, setKeyword] = useState('');
  const [skuKeyword, setSkuKeyword] = useState('');
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const [categoryId, setCategoryId] = useState<number | undefined>();
  const [brandId, setBrandId] = useState<number | undefined>();
  const [stockStatus, setStockStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [skuSearch, setSkuSearch] = useState('');
  const [skuKeywordRemote, setSkuKeywordRemote] = useState('');
  const threshold = 10;

  useEffect(() => {
    setEditor(null);
    setQ('');
    setSkuCode('');
    setKeyword('');
    setSkuKeyword('');
    setWarehouseId(undefined);
    setCategoryId(undefined);
    setBrandId(undefined);
    setStockStatus(undefined);
    setPage(1);
    setSkuSearch('');
    setSkuKeywordRemote('');
  }, [tenantId]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSkuKeywordRemote(skuSearch.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [skuSearch]);

  const filters = {
    q: keyword,
    skuCode: skuKeyword,
    warehouseId,
    categoryId,
    brandId,
    stockStatus,
    threshold,
    page,
    pageSize,
  };

  const listQuery = useQuery({
    queryKey: inventoryQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchInventory(filters, signal),
    enabled: tenantId != null,
  });

  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });

  const categoryQuery = useQuery({
    queryKey: productCategoriesQueryKey(tenantId),
    queryFn: ({ signal }) => fetchProductCategories(signal),
    enabled: tenantId != null,
  });

  const brandQuery = useQuery({
    queryKey: brandOptionsQueryKey(tenantId),
    queryFn: ({ signal }) => fetchBrandOptions(signal),
    enabled: tenantId != null,
  });

  const skuOptionsQuery = useQuery({
    queryKey: productSkuOptionsQueryKey(tenantId, { q: skuKeywordRemote, page: 1, pageSize: 20 }),
    queryFn: ({ signal }) =>
      fetchSkuOptions({ q: skuKeywordRemote || undefined, page: 1, pageSize: 20 }, signal),
    enabled: tenantId != null && editor?.type === 'initialize',
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory-transactions'] });
  };

  const initializeMutation = useMutation({
    mutationFn: initializeInventory,
    onSuccess: () => {
      message.success('库存已初始化');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '初始化失败');
    },
  });

  const adjustMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { type: 'ADJUST_IN' | 'ADJUST_OUT'; quantity: number; remark?: string | null } }) =>
      adjustInventory(id, payload),
    onSuccess: () => {
      message.success('库存已调整');
      setEditor(null);
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '调整失败');
    },
  });

  const warehouseOptions = useMemo(
    () => (warehouseQuery.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name} (${item.code})` })),
    [warehouseQuery.data],
  );

  const columns: ColumnsType<InventoryItem> = [
    { title: '商品', dataIndex: 'product_name', key: 'product_name' },
    { title: 'SKU', dataIndex: 'sku_code', key: 'sku_code', width: 140 },
    {
      title: '规格',
      key: 'spec',
      width: 160,
      render: (_, record) => specValuesLabel(record.spec_values),
    },
    { title: '仓库', dataIndex: 'warehouse_name', key: 'warehouse_name', width: 140 },
    { title: '实际库存', dataIndex: 'quantity', key: 'quantity', width: 100 },
    { title: '预占库存', dataIndex: 'reserved_quantity', key: 'reserved_quantity', width: 100 },
    { title: '可用库存', dataIndex: 'available_quantity', key: 'available_quantity', width: 100 },
    {
      title: '状态',
      key: 'stock_status',
      width: 90,
      render: (_, record) => stockTag(record, threshold),
    },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 180 },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Button type="link" size="small" onClick={() => navigate(`/inventory/${record.id}`)}>
            详情
          </Button>
          <Can permission={PERMISSION_CODE.inventoryAdjust}>
            <Button type="link" size="small" onClick={() => setEditor({ type: 'adjust', inventory: record })}>
              调整
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.inventoryTransactionRead}>
            <Button
              type="link"
              size="small"
              onClick={() => navigate(`/inventory/transactions?inventoryId=${record.id}`)}
            >
              流水
            </Button>
          </Can>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={props.title ?? '库存列表'}
        description={
          props.description ??
          '库存按仓库 + SKU 记账。可用库存 = 实际库存 - 预占库存，不单独存库。'
        }
        extra={
          <Can permission={PERMISSION_CODE.inventoryInitialize}>
            <Button type="primary" onClick={() => setEditor({ type: 'initialize' })}>
              初始化库存
            </Button>
          </Can>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          className="w-48"
          placeholder="商品 / SKU 名称"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          onPressEnter={() => {
            setKeyword(q.trim());
            setPage(1);
          }}
          allowClear
        />
        <Input
          className="w-40"
          placeholder="SKU 编码"
          value={skuCode}
          onChange={(event) => setSkuCode(event.target.value)}
          onPressEnter={() => {
            setSkuKeyword(skuCode.trim());
            setPage(1);
          }}
          allowClear
        />
        <Select
          className="w-44"
          allowClear
          placeholder="仓库"
          value={warehouseId}
          onChange={(value) => {
            setWarehouseId(value);
            setPage(1);
          }}
          options={warehouseOptions}
        />
        <TreeSelect
          className="w-44"
          allowClear
          placeholder="类目"
          value={categoryId}
          treeData={toTreeData(categoryQuery.data ?? [])}
          onChange={(value) => {
            setCategoryId(value);
            setPage(1);
          }}
        />
        <Select
          className="w-40"
          allowClear
          placeholder="品牌"
          value={brandId}
          onChange={(value) => {
            setBrandId(value);
            setPage(1);
          }}
          options={(brandQuery.data ?? []).map((item) => ({ value: item.id, label: item.name }))}
        />
        <Select
          className="w-36"
          allowClear
          placeholder="库存状态"
          value={stockStatus}
          onChange={(value) => {
            setStockStatus(value);
            setPage(1);
          }}
          options={[
            { value: INVENTORY_STOCK_STATUS.inStock, label: '有库存' },
            { value: INVENTORY_STOCK_STATUS.zero, label: '零库存' },
            { value: INVENTORY_STOCK_STATUS.low, label: '低库存' },
          ]}
        />
        <Button
          onClick={() => {
            setKeyword(q.trim());
            setSkuKeyword(skuCode.trim());
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
        title={editor?.type === 'adjust' ? '调整库存' : '初始化库存'}
        open={editor != null}
        onClose={() => setEditor(null)}
        width={440}
        destroyOnHidden
      >
        {editor?.type === 'initialize' ? (
          <Form
            layout="vertical"
            onFinish={(values: { warehouse_id: number; sku_id: number; quantity: number; remark?: string }) => {
              initializeMutation.mutate({
                warehouse_id: values.warehouse_id,
                sku_id: values.sku_id,
                quantity: values.quantity,
                remark: values.remark?.trim() || null,
              });
            }}
          >
            <Form.Item name="warehouse_id" label="仓库" rules={[{ required: true, message: '请选择仓库' }]}>
              <Select options={warehouseOptions} placeholder="仅启用中的仓库" />
            </Form.Item>
            <Form.Item name="sku_id" label="SKU" rules={[{ required: true, message: '请选择 SKU' }]}>
              <Select
                showSearch
                filterOption={false}
                placeholder="按 SKU 编码或商品名称搜索"
                onSearch={setSkuSearch}
                options={(skuOptionsQuery.data?.items ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.sku_code} ${item.product_name} ${item.name}`,
                }))}
              />
            </Form.Item>
            <Form.Item
              name="quantity"
              label="初始化数量"
              rules={[{ required: true, message: '请输入数量' }]}
              extra="允许 0。同一仓库 + SKU 只能初始化一次，之后请用调整。"
            >
              <InputNumber className="w-full" min={0} precision={0} />
            </Form.Item>
            <Form.Item name="remark" label="备注">
              <Input.TextArea rows={3} maxLength={255} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={initializeMutation.isPending}>
              确认初始化
            </Button>
          </Form>
        ) : null}
        {editor?.type === 'adjust' ? (
          <AdjustForm
            inventory={editor.inventory}
            loading={adjustMutation.isPending}
            onSubmit={(payload) => adjustMutation.mutate({ id: editor.inventory.id, payload })}
          />
        ) : null}
      </Drawer>
    </div>
  );
}

function AdjustForm({
  inventory,
  loading,
  onSubmit,
}: {
  inventory: InventoryItem;
  loading: boolean;
  onSubmit: (payload: { type: 'ADJUST_IN' | 'ADJUST_OUT'; quantity: number; remark?: string | null }) => void;
}) {
  const [type, setType] = useState<'ADJUST_IN' | 'ADJUST_OUT'>(INVENTORY_TRANSACTION_TYPE.adjustIn);

  return (
    <Form
      layout="vertical"
      initialValues={{ type: INVENTORY_TRANSACTION_TYPE.adjustIn, quantity: 1 }}
      onFinish={(values: { type: 'ADJUST_IN' | 'ADJUST_OUT'; quantity: number; remark?: string }) => {
        if (values.type === INVENTORY_TRANSACTION_TYPE.adjustOut && !canAdjustOut(inventory.available_quantity, values.quantity)) {
          return;
        }
        onSubmit({
          type: values.type,
          quantity: values.quantity,
          remark: values.remark?.trim() || null,
        });
      }}
    >
      <p className="mb-3 text-sm text-slate-600">
        实际 {inventory.quantity}　预占 {inventory.reserved_quantity}　可用 {inventory.available_quantity}
      </p>
      <Form.Item name="type" label="调整类型" rules={[{ required: true }]}>
        <Select
          onChange={(value) => setType(value)}
          options={[
            { value: INVENTORY_TRANSACTION_TYPE.adjustIn, label: '增加库存' },
            { value: INVENTORY_TRANSACTION_TYPE.adjustOut, label: '减少库存' },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="quantity"
        label="调整数量"
        rules={[
          { required: true, message: '请输入调整数量' },
          {
            validator: async (_, value: number) => {
              if (type === INVENTORY_TRANSACTION_TYPE.adjustOut && value > inventory.available_quantity) {
                throw new Error('减少数量不能大于可用库存，否则会把已预占的数量减没');
              }
            },
          },
        ]}
      >
        <InputNumber className="w-full" min={1} precision={0} />
      </Form.Item>
      <Form.Item name="remark" label="备注">
        <Input.TextArea rows={3} maxLength={255} />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={loading}>
        确认调整
      </Button>
    </Form>
  );
}
