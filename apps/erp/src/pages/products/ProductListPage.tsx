import {
  ApiError,
  brandOptionsQueryKey,
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  PRODUCT_STATUS,
  productCategoriesQueryKey,
  productsQueryKey,
  type ProductCategory,
  type ProductListItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Select, Space, Table, Tag, TreeSelect } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchBrandOptions, fetchProductCategories } from '@/api/catalog';
import { fetchProducts, updateProduct } from '@/api/products';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

const STATUS_LABEL: Record<string, string> = {
  [PRODUCT_STATUS.draft]: '草稿',
  [PRODUCT_STATUS.active]: '启用',
  [PRODUCT_STATUS.inactive]: '停用',
};

function statusColor(status: string) {
  if (status === PRODUCT_STATUS.active) {
    return 'success';
  }
  if (status === PRODUCT_STATUS.inactive) {
    return 'default';
  }
  return 'processing';
}

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

export function ProductListPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [skuCode, setSkuCode] = useState('');
  const [keyword, setKeyword] = useState('');
  const [skuKeyword, setSkuKeyword] = useState('');
  const [categoryId, setCategoryId] = useState<number | undefined>();
  const [brandId, setBrandId] = useState<number | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setQ('');
    setSkuCode('');
    setKeyword('');
    setSkuKeyword('');
    setCategoryId(undefined);
    setBrandId(undefined);
    setStatus(undefined);
    setPage(1);
  }, [tenantId]);

  const filters = {
    q: keyword,
    skuCode: skuKeyword,
    categoryId,
    brandId,
    status,
    page,
    pageSize,
  };

  const productsQuery = useQuery({
    queryKey: productsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchProducts(filters, signal),
    enabled: tenantId != null,
  });
  const categoriesQuery = useQuery({
    queryKey: productCategoriesQueryKey(tenantId),
    queryFn: ({ signal }) => fetchProductCategories(signal),
    enabled: tenantId != null,
  });
  const brandsQuery = useQuery({
    queryKey: brandOptionsQueryKey(tenantId),
    queryFn: ({ signal }) => fetchBrandOptions(signal),
    enabled: tenantId != null,
  });

  const categoryTree = useMemo(
    () => toTreeData(categoriesQuery.data ?? []),
    [categoriesQuery.data],
  );

  const statusMutation = useMutation({
    mutationFn: (values: { id: number; status: string }) =>
      updateProduct(values.id, { status: values.status }),
    onSuccess: () => {
      message.success('状态已更新');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'products'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'product'] });
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '更新失败');
    },
  });

  const columns: ColumnsType<ProductListItem> = [
    { title: '商品名称', dataIndex: 'name', key: 'name' },
    { title: '编码', dataIndex: 'code', key: 'code', width: 140 },
    { title: '类目', dataIndex: 'category_name', key: 'category_name', width: 140 },
    {
      title: '品牌',
      dataIndex: 'brand_name',
      key: 'brand_name',
      width: 120,
      render: (name: string | null) => name || '-',
    },
    { title: 'SKU 数量', dataIndex: 'sku_count', key: 'sku_count', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (value: string) => <Tag color={statusColor(value)}>{STATUS_LABEL[value] ?? value}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => value.replace('T', ' ').slice(0, 19),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Can permission={PERMISSION_CODE.productRead}>
            <Button type="link" size="small" onClick={() => navigate(`/products/${record.id}`)}>
              查看
            </Button>
          </Can>
          <Can permission={PERMISSION_CODE.productUpdate}>
            <Button type="link" size="small" onClick={() => navigate(`/products/${record.id}/edit`)}>
              编辑
            </Button>
            <Button
              type="link"
              size="small"
              onClick={() =>
                statusMutation.mutate({
                  id: record.id,
                  status:
                    record.status === PRODUCT_STATUS.active
                      ? PRODUCT_STATUS.inactive
                      : PRODUCT_STATUS.active,
                })
              }
            >
              {record.status === PRODUCT_STATUS.active ? '停用' : '启用'}
            </Button>
          </Can>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={props.title ?? '商品列表'}
        description={props.description ?? 'SPU 档案。库存后续只关联 SKU，不直接挂在商品上。'}
        extra={
          <Can permission={PERMISSION_CODE.productCreate}>
            <Button type="primary" onClick={() => navigate('/products/create')}>
              新增商品
            </Button>
          </Can>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          className="w-48!"
          placeholder="名称 / 商品编码"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          onPressEnter={() => {
            setKeyword(q.trim());
            setPage(1);
          }}
          allowClear
        />
        <Input
          className="w-44!"
          placeholder="SKU 编码"
          value={skuCode}
          onChange={(event) => setSkuCode(event.target.value)}
          onPressEnter={() => {
            setSkuKeyword(skuCode.trim());
            setPage(1);
          }}
          allowClear
        />
        <TreeSelect
          className="w-52"
          allowClear
          placeholder="类目"
          value={categoryId}
          treeData={categoryTree}
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
          options={(brandsQuery.data ?? []).map((item) => ({ value: item.id, label: item.name }))}
        />
        <Select
          className="w-32"
          allowClear
          placeholder="状态"
          value={status}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          options={[
            { value: PRODUCT_STATUS.draft, label: '草稿' },
            { value: PRODUCT_STATUS.active, label: '启用' },
            { value: PRODUCT_STATUS.inactive, label: '停用' },
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
        dataSource={productsQuery.data?.items ?? []}
        loading={productsQuery.isLoading}
        pagination={{
          current: page,
          pageSize,
          total: productsQuery.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage);
            setPageSize(nextSize);
          },
        }}
      />
    </div>
  );
}
