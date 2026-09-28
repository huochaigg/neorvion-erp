import {
  PERMISSION_CODE,
  PRODUCT_STATUS,
  productQueryKey,
  SKU_STATUS,
  type ProductSku,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Descriptions, Space, Spin, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchProduct } from '@/api/products';
import { Can } from '@/components/Can';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

const PRODUCT_STATUS_LABEL: Record<string, string> = {
  [PRODUCT_STATUS.draft]: '草稿',
  [PRODUCT_STATUS.active]: '启用',
  [PRODUCT_STATUS.inactive]: '停用',
};

function formatSpecs(values: Record<string, string>) {
  const entries = Object.entries(values);
  if (!entries.length) {
    return '-';
  }
  return entries.map(([key, value]) => `${key}: ${value}`).join('；');
}

export function ProductDetailPage(props: PageProps) {
  const navigate = useNavigate();
  const params = useParams();
  const productId = params.id ? Number(params.id) : null;
  const { tenantId } = usePermissions();
  const query = useQuery({
    queryKey: productQueryKey(tenantId, productId),
    queryFn: ({ signal }) => fetchProduct(productId as number, signal),
    enabled: tenantId != null && productId != null && Number.isFinite(productId),
  });

  const skuColumns: ColumnsType<ProductSku> = [
    { title: 'SKU 编码', dataIndex: 'sku_code', key: 'sku_code', width: 180 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '条码',
      dataIndex: 'barcode',
      key: 'barcode',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '规格',
      dataIndex: 'spec_values',
      key: 'spec_values',
      render: (values: Record<string, string>) => formatSpecs(values),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (value: string) => (
        <Tag color={value === SKU_STATUS.active ? 'success' : 'default'}>
          {value === SKU_STATUS.active ? '启用' : '停用'}
        </Tag>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={props.title ?? '商品详情'}
        description={props.description ?? 'SPU 基础信息与全部 SKU。后续库存挂 SKU。'}
        extra={
          <Space>
            <Button onClick={() => navigate('/products/list')}>返回列表</Button>
            {productId ? (
              <Can permission={PERMISSION_CODE.productUpdate}>
                <Button type="primary" onClick={() => navigate(`/products/${productId}/edit`)}>
                  编辑
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {query.isLoading ? <Spin /> : null}
      {query.isError ? (
        <Alert type="error" showIcon title="无法加载商品" description="可能不属于当前企业，或没有查看权限。" />
      ) : null}
      {query.data ? (
        <div className="flex flex-col gap-4">
          <Card title="基础信息">
            <Descriptions column={{ xs: 1, md: 2 }}>
              <Descriptions.Item label="名称">{query.data.name}</Descriptions.Item>
              <Descriptions.Item label="编码">{query.data.code}</Descriptions.Item>
              <Descriptions.Item label="类目">{query.data.category_name}</Descriptions.Item>
              <Descriptions.Item label="品牌">{query.data.brand_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                {PRODUCT_STATUS_LABEL[query.data.status] ?? query.data.status}
              </Descriptions.Item>
              <Descriptions.Item label="SKU 数量">{query.data.skus.length}</Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                {query.data.description || '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="SKU">
            <Table
              rowKey="id"
              columns={skuColumns}
              dataSource={query.data.skus}
              pagination={false}
            />
          </Card>
        </div>
      ) : null}
    </div>
  );
}
