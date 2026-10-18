import {
  ApiError,
  canConfirmReturnInbound,
  canReceiveReturn,
  canUpdateReturnLogistics,
  defaultInboundQuantity,
  PERMISSION_CODE,
  RETURN_CONDITION,
  RETURN_CONDITION_OPTIONS,
  returnConditionLabel,
  returnOrderQueryKey,
  returnOrderStatusLabel,
  specValuesLabel,
  type ReturnOrderItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Descriptions, Input, InputNumber, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  confirmReturnInbound,
  fetchReturnOrder,
  receiveReturnOrder,
  updateReturnOrder,
} from '@/api/return-orders';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

interface ReceiveDraft {
  received_quantity: number;
  condition: string;
  remark: string;
}

export function ReturnOrderDetailPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const returnId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<number, ReceiveDraft>>({});
  const [trackingNo, setTrackingNo] = useState('');
  const [carrierName, setCarrierName] = useState('');

  const query = useQuery({
    queryKey: returnOrderQueryKey(tenantId, returnId),
    queryFn: ({ signal }) => fetchReturnOrder(returnId, signal),
    enabled: tenantId != null && returnId > 0,
  });
  const order = query.data;

  useEffect(() => {
    if (!order) {
      return;
    }
    const next: Record<number, ReceiveDraft> = {};
    for (const item of order.items) {
      next[item.id] = {
        received_quantity: 0,
        condition: item.condition || RETURN_CONDITION.good,
        remark: item.remark ?? '',
      };
    }
    setDraft(next);
    setTrackingNo(order.tracking_no ?? '');
    setCarrierName(order.carrier_name ?? '');
  }, [order]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'return-orders'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'return-order'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sale'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sales'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory-transactions'] });
  };

  const receiveMutation = useMutation({
    mutationFn: (
      items: Array<{
        item_id: number;
        received_quantity: number;
        condition: string;
        remark: string | null;
      }>,
    ) => receiveReturnOrder(returnId, { items }),
    onSuccess: () => {
      message.success('已登记收货');
      invalidate();
    },
    onError: (error: unknown) => message.error(error instanceof ApiError ? error.message : '收货失败'),
  });

  const inboundMutation = useMutation({
    mutationFn: () => confirmReturnInbound(returnId),
    onSuccess: () => {
      message.success('已确认退货入库');
      invalidate();
    },
    onError: (error: unknown) => message.error(error instanceof ApiError ? error.message : '入库失败'),
  });

  const columns: ColumnsType<ReturnOrderItem> = [
    { title: '商品', dataIndex: 'product_name', width: 150, render: (value: string) => <EllipsisCell value={value} /> },
    { title: 'SKU', dataIndex: 'sku_code', width: 140, render: (value: string) => <CodeCell value={value} /> },
    {
      title: '规格',
      key: 'spec',
      width: 130,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    { title: '批准退货', dataIndex: 'expected_quantity', width: 90 },
    { title: '累计已收', dataIndex: 'received_quantity', width: 90 },
    { title: '已入库', dataIndex: 'inbound_quantity', width: 80 },
    {
      title: '质量状态',
      dataIndex: 'condition',
      width: 110,
      render: (value: string) => returnConditionLabel(value),
    },
    {
      title: '本次收到',
      key: 'received_now',
      width: 110,
      render: (_, record) => (
        <InputNumber
          min={0}
          max={Math.max(record.expected_quantity - record.received_quantity, 0)}
          disabled={!order || !canReceiveReturn(order.status)}
          value={draft[record.id]?.received_quantity ?? 0}
          onChange={(value) => {
            setDraft((prev) => ({
              ...prev,
              [record.id]: { ...prev[record.id], received_quantity: Number(value ?? 0) },
            }));
          }}
        />
      ),
    },
    {
      title: '收货质量',
      key: 'condition_edit',
      width: 130,
      render: (_, record) => (
        <Select
          style={{ width: 120 }}
          disabled={!order || !canReceiveReturn(order.status)}
          options={RETURN_CONDITION_OPTIONS}
          value={draft[record.id]?.condition}
          onChange={(value) => {
            setDraft((prev) => ({
              ...prev,
              [record.id]: { ...prev[record.id], condition: value },
            }));
          }}
        />
      ),
    },
    {
      title: '预计入库',
      key: 'inbound_hint',
      width: 90,
      render: (_, record) => {
        const condition = draft[record.id]?.condition ?? record.condition;
        const received = record.received_quantity + (draft[record.id]?.received_quantity ?? 0);
        return defaultInboundQuantity(condition, received);
      },
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '退货单详情'}
        description={props.description}
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/return-orders')}>返回列表</Button>
            {order ? (
              <Button onClick={() => navigate(`/after-sales/${order.after_sale_order_id}`)}>售后单</Button>
            ) : null}
            {order && canUpdateReturnLogistics(order.status) ? (
              <Can permission={PERMISSION_CODE.returnOrderReceive}>
                <Button
                  onClick={() => {
                    void updateReturnOrder(returnId, {
                      tracking_no: trackingNo.trim() || null,
                      carrier_name: carrierName.trim() || null,
                    }).then(
                      () => message.success('已保存物流信息'),
                      (error: unknown) => message.error(error instanceof ApiError ? error.message : '保存失败'),
                    );
                  }}
                >
                  保存物流
                </Button>
              </Can>
            ) : null}
            {order && canReceiveReturn(order.status) ? (
              <Can permission={PERMISSION_CODE.returnOrderReceive}>
                <Button
                  type="primary"
                  loading={receiveMutation.isPending}
                  onClick={() => {
                    const items = (order?.items ?? [])
                      .map((item) => ({
                        item_id: item.id,
                        received_quantity: draft[item.id]?.received_quantity ?? 0,
                        condition: draft[item.id]?.condition ?? item.condition,
                        remark: draft[item.id]?.remark || null,
                      }))
                      .filter((item) => item.received_quantity > 0);
                    if (items.length === 0) {
                      message.warning('请至少填写一条本次收到数量');
                      return;
                    }
                    receiveMutation.mutate(items);
                  }}
                >
                  登记收货
                </Button>
              </Can>
            ) : null}
            {order && canConfirmReturnInbound(order.status, order.received_quantity) ? (
              <Can permission={PERMISSION_CODE.returnOrderInbound}>
                <Button
                  type="primary"
                  loading={inboundMutation.isPending}
                  onClick={() => {
                    modal.confirm({
                      title: '确认退货入库？',
                      content: '只有质量状态为「正常」的数量会进入普通可用库存。残次品本版不计入普通库存。',
                      onOk: () => inboundMutation.mutateAsync(),
                    });
                  }}
                >
                  确认退货入库
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {order ? (
        <>
          <Alert
            className="mb-4"
            type="info"
            showIcon
            message="当前版本暂不将残次品计入普通可用库存。"
          />
          <Card className="mb-4">
            <Descriptions column={2} size="small">
              <Descriptions.Item label="退货单号">{order.return_no}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag>{returnOrderStatusLabel(order.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="售后单">{order.after_sale_no}</Descriptions.Item>
              <Descriptions.Item label="销售订单">{order.sales_order_no}</Descriptions.Item>
              <Descriptions.Item label="客户">{order.customer_name}</Descriptions.Item>
              <Descriptions.Item label="退货仓库">{order.warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="预期 / 已收 / 已入库">
                {order.expected_quantity} / {order.received_quantity} / {order.inbound_quantity}
              </Descriptions.Item>
              <Descriptions.Item label="收货时间">{formatDateTime(order.received_at)}</Descriptions.Item>
            </Descriptions>
            {canUpdateReturnLogistics(order.status) ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Input
                  style={{ width: 220 }}
                  placeholder="客户退回物流单号"
                  value={trackingNo}
                  onChange={(event) => setTrackingNo(event.target.value)}
                />
                <Input
                  style={{ width: 220 }}
                  placeholder="承运商名称"
                  value={carrierName}
                  onChange={(event) => setCarrierName(event.target.value)}
                />
              </div>
            ) : null}
          </Card>
          <Card title="退货明细" className='mt-4!'>
            <AppTable rowKey="id" size="small" columns={columns} dataSource={order.items} pagination={false} fillHeight={false} />
          </Card>
        </>
      ) : null}
    </FormPageContainer>
  );
}
