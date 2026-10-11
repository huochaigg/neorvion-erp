import {
  ApiError,
  canConfirmPurchaseReturnOutbound,
  PERMISSION_CODE,
  purchaseReturnOutboundQueryKey,
  purchaseReturnOutboundStatusLabel,
  specValuesLabel,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Space, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import {
  cancelPurchaseReturnOutbound,
  confirmPurchaseReturnOutbound,
  fetchPurchaseReturnOutbound,
} from '@/api/purchase-return-outbounds';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function PurchaseReturnOutboundDetailPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const outboundId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: purchaseReturnOutboundQueryKey(tenantId, outboundId),
    queryFn: ({ signal }) => fetchPurchaseReturnOutbound(outboundId, signal),
    enabled: tenantId != null && outboundId > 0,
  });
  const order = query.data;
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-return-outbounds'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-return-outbound'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-return'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-returns'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-order'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory-transactions'] });
  };
  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '退货出库详情'}
        description={props.description}
        extra={
          <Space>
            <Button onClick={() => navigate('/purchase-return-outbounds')}>返回列表</Button>
            {order ? (
              <Button onClick={() => navigate(`/purchase-returns/${order.purchase_return_id}`)}>采购退货单</Button>
            ) : null}
            {order && canConfirmPurchaseReturnOutbound(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseReturnOutbound}>
                <Button
                  type="primary"
                  onClick={() => {
                    modal.confirm({
                      title: '确认退货出库',
                      content: '确认后将正式减少当前仓库库存，并生成采购退货库存流水，操作不可直接撤销。',
                      onOk: async () => {
                        await confirmPurchaseReturnOutbound(outboundId);
                        message.success('已确认出库');
                        invalidate();
                      },
                    });
                  }}
                >
                  确认退货出库
                </Button>
                <Button
                  danger
                  onClick={() => {
                    cancelPurchaseReturnOutbound(outboundId)
                      .then(() => {
                        message.success('已取消');
                        invalidate();
                      })
                      .catch((error: unknown) =>
                        message.error(error instanceof ApiError ? error.message : '取消失败'),
                      );
                  }}
                >
                  取消草稿
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {order ? (
        <>
          <Card className="mb-4">
            <Descriptions column={3} size="small">
              <Descriptions.Item label="出库单号">{order.outbound_no}</Descriptions.Item>
              <Descriptions.Item label="采购退货单">{order.purchase_return_no}</Descriptions.Item>
              <Descriptions.Item label="原采购单">{order.purchase_order_no}</Descriptions.Item>
              <Descriptions.Item label="供应商">{order.supplier_name}</Descriptions.Item>
              <Descriptions.Item label="仓库">{order.warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag>{purchaseReturnOutboundStatusLabel(order.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="确认时间">
                {order.confirmed_at ? formatDateTime(order.confirmed_at) : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <AppTable
            rowKey="id"
            fillHeight={false}
            pagination={false}
            dataSource={order.items}
            columns={[
              {
                title: '商品',
                dataIndex: 'product_name',
                width: 150,
                render: (value: string) => <EllipsisCell value={value} />,
              },
              { title: 'SKU', dataIndex: 'sku_code', width: 130, render: (value: string) => <CodeCell value={value} /> },
              {
                title: '规格',
                key: 'spec',
                width: 120,
                render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
              },
              { title: '批准', dataIndex: 'approved_return_quantity', width: 80 },
              { title: '累计已退', dataIndex: 'already_returned_quantity', width: 90 },
              { title: '剩余待退', dataIndex: 'remaining_return_quantity', width: 90 },
              { title: '当前可用', dataIndex: 'inventory_available', width: 90 },
              { title: '本次数量', dataIndex: 'quantity', width: 90 },
            ]}
          />
        </>
      ) : null}
    </FormPageContainer>
  );
}
