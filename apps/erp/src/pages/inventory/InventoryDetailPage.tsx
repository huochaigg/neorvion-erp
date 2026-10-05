import {
  ApiError,
  inventoryDetailQueryKey,
  inventoryTransactionTypeLabel,
  PERMISSION_CODE,
  specValuesLabel,
  type InventoryTransaction,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Descriptions, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchInventoryDetail } from '@/api/inventory';
import { AppTable, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

export function InventoryDetailPage(props: PageProps) {
  const navigate = useNavigate();
  const { tenantId } = usePermissions();
  const params = useParams();
  const inventoryId = Number(params.id);
  const validId = Number.isInteger(inventoryId) && inventoryId > 0;

  const detailQuery = useQuery({
    queryKey: inventoryDetailQueryKey(tenantId, validId ? inventoryId : null),
    queryFn: ({ signal }) => fetchInventoryDetail(inventoryId, signal),
    enabled: tenantId != null && validId,
  });

  const item = detailQuery.data;
  const columns: ColumnsType<InventoryTransaction> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 110,
      render: (value: string) => inventoryTransactionTypeLabel(value),
    },
    { title: '变化数量', dataIndex: 'change_quantity', key: 'change_quantity', width: 100 },
    {
      title: '实际库存',
      key: 'qty',
      width: 140,
      render: (_, record) => `${record.before_quantity} → ${record.after_quantity}`,
    },
    {
      title: '预占',
      key: 'reserved',
      width: 140,
      render: (_, record) => `${record.before_reserved_quantity} → ${record.after_reserved_quantity}`,
    },
    {
      title: '操作人',
      dataIndex: 'operator_name',
      key: 'operator_name',
      width: 120,
      render: (value: string | null) => <EllipsisCell value={value || '-'} />,
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      width: 200,
      render: (value: string | null) => <EllipsisCell value={value || '-'} />,
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '库存详情'}
        description={props.description ?? '查看仓库 + SKU 的当前账面与最近流水。version 仅用于开发排查乐观锁。'}
        extra={
          <Space>
            <Button onClick={() => navigate('/inventory/list')}>返回列表</Button>
            {item ? (
              <Can permission={PERMISSION_CODE.inventoryTransactionRead}>
                <Button onClick={() => navigate(`/inventory/transactions?inventoryId=${item.id}`)}>
                  全部流水
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {detailQuery.isError ? (
        <p className="text-sm text-red-600">
          {detailQuery.error instanceof ApiError ? detailQuery.error.message : '加载失败'}
        </p>
      ) : null}
      {item ? (
        <>
          <Card className="mb-4">
            <Descriptions column={2} size="small">
              <Descriptions.Item label="商品">{item.product_name}</Descriptions.Item>
              <Descriptions.Item label="SKU">{item.sku_code}</Descriptions.Item>
              <Descriptions.Item label="SKU 名称">{item.sku_name}</Descriptions.Item>
              <Descriptions.Item label="规格">{specValuesLabel(item.spec_values)}</Descriptions.Item>
              <Descriptions.Item label="仓库">{item.warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="实际库存">{item.quantity}</Descriptions.Item>
              <Descriptions.Item label="预占库存">{item.reserved_quantity}</Descriptions.Item>
              <Descriptions.Item label="可用库存">{item.available_quantity}</Descriptions.Item>
              <Descriptions.Item label="version">
                <Tag>{item.version}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">{formatDateTime(item.updated_at)}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="最近流水">
            <AppTable
              rowKey="id"
              size="small"
              columns={columns}
              dataSource={item.recent_transactions}
              pagination={false}
              fillHeight={false}
            />
          </Card>
        </>
      ) : null}
    </FormPageContainer>
  );
}
