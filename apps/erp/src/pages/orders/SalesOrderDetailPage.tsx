import {
  ApiError,
  canCancelSalesOrder,
  canConfirmSalesOrder,
  canCreateOutbound,
  canEditSalesOrder,
  canSubmitSalesOrder,
  formatSalesAmount,
  formatSalesInventoryShortage,
  PERMISSION_CODE,
  salesOrderQueryKey,
  salesOrderSourceLabel,
  salesOrderStatusLabel,
  specValuesLabel,
  type SalesOrderDetail,
  type SalesOrderItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Input, Space, Tag, Timeline } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useParams } from 'react-router-dom';
import { cancelSalesOrder, confirmSalesOrder, fetchSalesOrder, submitSalesOrder } from '@/api/sales-orders';
import { createOutboundOrder, fetchOutboundOrders } from '@/api/outbound-orders';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

function statusTag(status: string) {
  const color =
    status === 'PENDING_CONFIRMATION'
      ? 'processing'
      : status === 'WAITING_OUTBOUND' || status === 'PARTIALLY_SHIPPED'
        ? 'blue'
        : status === 'SHIPPED'
          ? 'success'
          : 'default';
  return <Tag color={color}>{salesOrderStatusLabel(status)}</Tag>;
}

function errorText(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) {
    return fallback;
  }
  return formatSalesInventoryShortage(error.data, error.message || fallback);
}

function addressText(order: SalesOrderDetail) {
  const parts = [order.country_code, order.province, order.city, order.address].filter(Boolean);
  return parts.length ? parts.join(' ') : '-';
}

export function SalesOrderDetailPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const params = useParams();
  const orderId = Number(params.id);
  const validId = Number.isInteger(orderId) && orderId > 0;

  const detailQuery = useQuery({
    queryKey: salesOrderQueryKey(tenantId, validId ? orderId : null),
    queryFn: ({ signal }) => fetchSalesOrder(orderId, signal),
    enabled: tenantId != null && validId,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-orders'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-order'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory-transactions'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sku-inventory'] });
  };

  const submitMutation = useMutation({
    mutationFn: submitSalesOrder,
    onSuccess: () => {
      message.success('已提交，等待确认');
      invalidate();
    },
    onError: (error: unknown) => message.error(errorText(error, '提交失败')),
  });
  const confirmMutation = useMutation({
    mutationFn: confirmSalesOrder,
    onSuccess: () => {
      message.success('已确认并预占库存');
      invalidate();
    },
    onError: (error: unknown) => message.error(errorText(error, '确认失败')),
  });

  const order = detailQuery.data;
  const columns: ColumnsType<SalesOrderItem> = [
    { title: '商品', dataIndex: 'product_name', key: 'product_name', width: 160, render: (value: string) => <EllipsisCell value={value} /> },
    { title: 'SKU', dataIndex: 'sku_code', key: 'sku_code', width: 150, render: (value: string) => <CodeCell value={value} /> },
    {
      title: '规格',
      key: 'spec',
      width: 140,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    { title: '购买数量', dataIndex: 'quantity', key: 'quantity', width: 100 },
    { title: '已预占', dataIndex: 'reserved_quantity', key: 'reserved_quantity', width: 90 },
    { title: '已出库', dataIndex: 'shipped_quantity', key: 'shipped_quantity', width: 90 },
    {
      title: '剩余待出库',
      key: 'remaining',
      width: 110,
      render: (_, record) => record.quantity - record.shipped_quantity,
    },
    {
      title: '单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 100,
      render: (value: number | null) => formatSalesAmount(value),
    },
    {
      title: '金额',
      dataIndex: 'line_amount',
      key: 'line_amount',
      width: 100,
      render: (value: number | null) => formatSalesAmount(value),
    },
    {
      title: '当前库存（实际 / 预占 / 可用）',
      key: 'stock',
      width: 220,
      render: (_, record) => {
        if (record.current_quantity == null) {
          return '未建库存';
        }
        return `${record.current_quantity} / ${record.current_reserved_quantity} / ${record.current_available_quantity}`;
      },
    },
  ];

  const timeline = order
    ? [
        { children: `创建 ${formatDateTime(order.created_at)} ${order.created_by_name ?? ''}` },
        order.submitted_at ? { children: `提交 ${formatDateTime(order.submitted_at)}` } : null,
        order.confirmed_at
          ? { children: `确认并预占 ${formatDateTime(order.confirmed_at)} ${order.confirmed_by_name ?? ''}` }
          : null,
        order.cancelled_at
          ? {
              color: 'red',
              children: `取消 ${formatDateTime(order.cancelled_at)} ${order.cancel_reason ?? ''}`,
            }
          : null,
      ].filter((item) => item != null)
    : [];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '销售订单详情'}
        description={props.description ?? '收货地址是下单快照。当前库存数字只供参考，不是订单历史。'}
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/orders/list')}>返回列表</Button>
            {order && canEditSalesOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.orderUpdate}>
                <Button onClick={() => navigate(`/orders/${order.id}/edit`)}>编辑</Button>
              </Can>
            ) : null}
            {order && canSubmitSalesOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.orderSubmit}>
                <Button type="primary" loading={submitMutation.isPending} onClick={() => submitMutation.mutate(order.id)}>
                  提交
                </Button>
              </Can>
            ) : null}
            {order && canConfirmSalesOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.orderAudit}>
                <Button type="primary" loading={confirmMutation.isPending} onClick={() => confirmMutation.mutate(order.id)}>
                  确认订单
                </Button>
              </Can>
            ) : null}
            {order && canCreateOutbound(order.status) ? (
              <Can permission={PERMISSION_CODE.outboundCreate}>
                <Button
                  type="primary"
                  onClick={async () => {
                    try {
                      const existing = await fetchOutboundOrders({
                        salesOrderId: order.id,
                        page: 1,
                        pageSize: 20,
                      });
                      const open = existing.items.find(
                        (item) => item.status === 'PENDING_PICKING' || item.status === 'PICKED',
                      );
                      if (open) {
                        navigate(`/outbound-orders/${open.id}`);
                        return;
                      }
                      const created = await createOutboundOrder(order.id);
                      message.success('已生成出库单');
                      invalidate();
                      navigate(`/outbound-orders/${created.id}`);
                    } catch (error) {
                      message.error(error instanceof ApiError ? error.message : '生成出库单失败');
                    }
                  }}
                >
                  {order.status === 'PARTIALLY_SHIPPED' ? '继续出库' : '查看出库单'}
                </Button>
              </Can>
            ) : null}
            {order && order.status === 'SHIPPED' ? <Tag color="success">已全部出库</Tag> : null}
            {order && canCancelSalesOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.orderCancel}>
                <Button
                  danger
                  onClick={() => {
                    let reason = '';
                    modal.confirm({
                      title: order.status === 'WAITING_OUTBOUND' ? '取消并释放库存预占' : '取消销售订单',
                      content: (
                        <Input.TextArea
                          rows={3}
                          maxLength={255}
                          placeholder="取消原因（可选）"
                          onChange={(event) => {
                            reason = event.target.value;
                          }}
                        />
                      ),
                      onOk: async () => {
                        try {
                          await cancelSalesOrder(order.id, reason.trim() || null);
                          message.success(order.status === 'WAITING_OUTBOUND' ? '已取消并释放库存' : '已取消');
                          invalidate();
                        } catch (error) {
                          message.error(errorText(error, '取消失败'));
                          return Promise.reject(new Error('cancel failed'));
                        }
                      },
                    });
                  }}
                >
                  取消
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
      {order ? (
        <>
          <Card className="mb-4">
            <Timeline items={timeline} />
            <Descriptions column={2} size="small">
              <Descriptions.Item label="订单号">{order.order_no}</Descriptions.Item>
              <Descriptions.Item label="状态">{statusTag(order.status)}</Descriptions.Item>
              <Descriptions.Item label="来源">{salesOrderSourceLabel(order.source)}</Descriptions.Item>
              <Descriptions.Item label="平台订单号">{order.external_order_no || '-'}</Descriptions.Item>
              <Descriptions.Item label="客户">{order.customer_name}</Descriptions.Item>
              <Descriptions.Item label="履约仓库">{order.warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="收件人">{order.recipient_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="电话">{order.recipient_phone || '-'}</Descriptions.Item>
              <Descriptions.Item label="地址" span={2}>
                {addressText(order)}
              </Descriptions.Item>
              <Descriptions.Item label="创建人">{order.created_by_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(order.created_at)}</Descriptions.Item>
              <Descriptions.Item label="提交时间">{formatDateTime(order.submitted_at)}</Descriptions.Item>
              <Descriptions.Item label="确认时间">{formatDateTime(order.confirmed_at)}</Descriptions.Item>
              <Descriptions.Item label="取消信息" span={2}>
                {order.cancelled_at
                  ? `${formatDateTime(order.cancelled_at)} ${order.cancelled_by_name ?? ''} ${order.cancel_reason ?? ''}`
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="币种">{order.currency_code}</Descriptions.Item>
              <Descriptions.Item label="订单金额">{formatSalesAmount(order.total_amount)}</Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>
                {order.remark || '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="拣货记录" className="mt-4!">
            <AppTable
              rowKey="key"
              size="small"
              pagination={false}
              fillHeight={false}
              dataSource={(order.picks ?? []).flatMap((pick) =>
                pick.lines.map((line) => ({
                  key: `${pick.id}-${line.id}`,
                  picked_at: pick.picked_at,
                  picked_by_name: pick.picked_by_name,
                  outbound_no: pick.outbound_no,
                  sku_code: line.sku_code,
                  product_name: line.product_name,
                  quantity: line.quantity,
                  change: `${line.picked_before} → ${line.picked_after}`,
                })),
              )}
              locale={{ emptyText: '还没有拣货记录' }}
              columns={[
                {
                  title: '时间',
                  dataIndex: 'picked_at',
                  width: 170,
                  render: (value: string) => formatDateTime(value),
                },
                { title: '操作人', dataIndex: 'picked_by_name', width: 120, render: (value: string | null) => value || '-' },
                { title: '出库单', dataIndex: 'outbound_no', width: 160 },
                { title: 'SKU', dataIndex: 'sku_code', width: 140 },
                { title: '商品', dataIndex: 'product_name', width: 160 },
                { title: '本次拣货', dataIndex: 'quantity', width: 100 },
                { title: '累计变化', dataIndex: 'change', width: 120 },
              ]}
            />
          </Card>
          <Card title="订单明细" className="mt-4!">
            <AppTable rowKey="id" size="small" columns={columns} dataSource={order.items} pagination={false} fillHeight={false} />
          </Card>
        </>
      ) : null}
    </FormPageContainer>
  );
}
