import {
  ApiError,
  inventoryQueryKey,
  inventoryTransactionsQueryKey,
  canCreateShipmentFromOutbound,
  outboundOrderQueryKey,
  outboundOrdersQueryKey,
  PERMISSION_CODE,
  salesOrderQueryKey,
  salesOrdersQueryKey,
  shipmentStatusLabel,
  shipmentsQueryKey,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Descriptions, InputNumber, Popconfirm, Space, Table, Tag } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  cancelOutboundOrder,
  confirmOutboundOrder,
  fetchOutboundOrder,
  pickOutboundOrder,
} from '@/api/outbound-orders';
import { fetchShipments } from '@/api/shipments';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

const STATUS_LABEL: Record<string, string> = {
  PENDING_PICKING: '待拣货',
  PICKED: '已拣货',
  CONFIRMED: '已出库',
  CANCELLED: '已取消',
};

export function OutboundDetailPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const outboundId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: outboundOrderQueryKey(tenantId, outboundId),
    queryFn: ({ signal }) => fetchOutboundOrder(outboundId, signal),
    enabled: tenantId != null && outboundId > 0,
  });
  const order = query.data;
  const remainingShippable = (order?.items ?? []).reduce(
    (sum, item) => sum + (item.remaining_shippable_quantity ?? 0),
    0,
  );
  const shipmentsQuery = useQuery({
    queryKey: shipmentsQueryKey(tenantId, { outboundOrderId: outboundId, page: 1, pageSize: 50 }),
    queryFn: ({ signal }) =>
      fetchShipments({ outboundOrderId: outboundId, page: 1, pageSize: 50 }, signal),
    enabled: tenantId != null && outboundId > 0,
  });
  const [picked, setPicked] = useState<Record<number, number>>({});
  useEffect(() => {
    if (!order) {
      return;
    }
    setPicked(
      Object.fromEntries(
        order.items.map((item) => [item.id, Math.max(item.planned_quantity - item.picked_quantity, 0)]),
      ),
    );
  }, [order]);

  function pickItems() {
    return (order?.items ?? [])
      .map((item) => ({
        id: item.id,
        picked_quantity: picked[item.id] ?? 0,
        remaining: item.planned_quantity - item.picked_quantity,
      }))
      .filter((item) => item.remaining > 0 && item.picked_quantity > 0)
      .map(({ id, picked_quantity }) => ({ id, picked_quantity }));
  }

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: outboundOrderQueryKey(tenantId, outboundId) });
    await queryClient.invalidateQueries({ queryKey: outboundOrdersQueryKey(tenantId) });
    await queryClient.invalidateQueries({
      queryKey: salesOrderQueryKey(tenantId, order?.sales_order_id ?? null),
    });
    await queryClient.invalidateQueries({ queryKey: salesOrdersQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: inventoryQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: inventoryTransactionsQueryKey(tenantId) });
  }

  const pickMutation = useMutation({
    mutationFn: (finish: boolean) => pickOutboundOrder(outboundId, pickItems(), finish),
    onSuccess: async (_data, finish) => {
      message.success(finish ? '拣货已结束，库存未变化' : '已记下本次拣货，还可以继续拣');
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '拣货失败');
    },
  });
  const confirmMutation = useMutation({
    mutationFn: () => confirmOutboundOrder(outboundId),
    onSuccess: async () => {
      message.success('已出库。实际库存和预占同时减少，可用量通常不变');
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '出库失败');
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelOutboundOrder(outboundId),
    onSuccess: async () => {
      message.success('已取消出库任务');
      await refresh();
    },
  });

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? order?.outbound_no ?? '出库单'}
        extra={
          <Space>
            <Button onClick={() => navigate('/outbound-orders')}>返回列表</Button>
            {order?.status === 'PENDING_PICKING' ? (
              <Can permission={PERMISSION_CODE.outboundPick}>
                <Space>
                  <Button loading={pickMutation.isPending} onClick={() => pickMutation.mutate(false)}>
                    记录本次拣货
                  </Button>
                  <Button type="primary" loading={pickMutation.isPending} onClick={() => pickMutation.mutate(true)}>
                    完成拣货
                  </Button>
                </Space>
              </Can>
            ) : null}
            {order?.status === 'PICKED' ? (
              <Can permission={PERMISSION_CODE.outboundConfirm}>
                <Popconfirm
                  title="确认后将正式扣减库存，是否继续？"
                  onConfirm={() => confirmMutation.mutate()}
                >
                  <Button type="primary" loading={confirmMutation.isPending}>
                    确认出库
                  </Button>
                </Popconfirm>
              </Can>
            ) : null}
            {order && canCreateShipmentFromOutbound(order.status, remainingShippable) ? (
              <Can permission={PERMISSION_CODE.shipmentCreate}>
                <Button type="primary" onClick={() => navigate(`/shipments/create?outboundOrderId=${order.id}`)}>
                  创建物流单
                </Button>
              </Can>
            ) : null}
            {order && (order.status === 'PENDING_PICKING' || order.status === 'PICKED') ? (
              <Can permission={PERMISSION_CODE.outboundCancel}>
                <Button danger loading={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
                  取消
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {order ? (
        <>
          <Descriptions column={3}>
            <Descriptions.Item label="销售订单">{order.sales_order_no}</Descriptions.Item>
            <Descriptions.Item label="客户">{order.customer_name}</Descriptions.Item>
            <Descriptions.Item label="仓库">{order.warehouse_name}</Descriptions.Item>
            <Descriptions.Item label="收件人">{order.recipient_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="地址">{order.address || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag>{STATUS_LABEL[order.status] ?? order.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="拣货时间">{formatDateTime(order.picked_at)}</Descriptions.Item>
            <Descriptions.Item label="出库时间">{formatDateTime(order.confirmed_at)}</Descriptions.Item>
          </Descriptions>
          {order.status === 'PENDING_PICKING' ? (
            <p className="mt-4! text-sm text-slate-500">
              本次数量默认是剩余计划。要分成几次拣时，先把数量改小，再点「记录本次拣货」。拣满或点「完成拣货」后才能确认出库。拣货不改变库存。
            </p>
          ) : null}
          <Table
            rowKey="id"
            pagination={false}
            dataSource={order.items}
            className="mt-4!"
            columns={[
              { title: 'SKU', dataIndex: 'sku_code' },
              { title: '商品', dataIndex: 'product_name' },
              { title: '计划数量', dataIndex: 'planned_quantity' },
              { title: '已拣累计', dataIndex: 'picked_quantity' },
              {
                title: '本次拣货',
                render: (_, row) => {
                  const remaining = row.planned_quantity - row.picked_quantity;
                  if (order.status !== 'PENDING_PICKING' || remaining <= 0) {
                    return '-';
                  }
                  return (
                    <InputNumber
                      min={1}
                      max={remaining}
                      value={picked[row.id] ?? remaining}
                      onChange={(value) =>
                        setPicked((current) => ({ ...current, [row.id]: Number(value || 0) }))
                      }
                    />
                  );
                },
              },
              { title: '出库数量', dataIndex: 'outbound_quantity' },
              { title: '已发货', dataIndex: 'shipped_quantity' },
              { title: '剩余待发', dataIndex: 'remaining_shippable_quantity' },
            ]}
          />
          <Table
            className="mt-4!"
            rowKey="id"
            pagination={false}
            locale={{ emptyText: '还没有物流单' }}
            dataSource={shipmentsQuery.data?.items ?? []}
            columns={[
              { title: '物流单号', dataIndex: 'shipment_no' },
              { title: '物流商', dataIndex: 'carrier_name' },
              { title: '运单号', dataIndex: 'tracking_no', render: (value: string | null) => value || '-' },
              {
                title: '状态',
                dataIndex: 'status',
                render: (value: string) => shipmentStatusLabel(value),
              },
              {
                title: '操作',
                render: (_, row) => (
                  <Button type="link" onClick={() => navigate(`/shipments/${row.id}`)}>
                    详情
                  </Button>
                ),
              },
            ]}
          />
          <Table
            className="mt-4!"
            rowKey="key"
            pagination={false}
            locale={{ emptyText: '还没有拣货记录' }}
            dataSource={(order.picks ?? []).flatMap((pick) =>
              pick.lines.map((line) => ({
                key: `${pick.id}-${line.id}`,
                picked_at: pick.picked_at,
                picked_by_name: pick.picked_by_name,
                sku_code: line.sku_code,
                product_name: line.product_name,
                quantity: line.quantity,
                change: `${line.picked_before} → ${line.picked_after}`,
              })),
            )}
            columns={[
              { title: '拣货时间', dataIndex: 'picked_at', render: (value: string) => formatDateTime(value) },
              { title: '操作人', dataIndex: 'picked_by_name', render: (value: string | null) => value || '-' },
              { title: 'SKU', dataIndex: 'sku_code' },
              { title: '商品', dataIndex: 'product_name' },
              { title: '本次拣货', dataIndex: 'quantity' },
              { title: '累计变化', dataIndex: 'change' },
            ]}
          />
        </>
      ) : null}
    </FormPageContainer>
  );
}
