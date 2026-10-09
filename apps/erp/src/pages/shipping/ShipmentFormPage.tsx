import {
  ApiError,
  CARRIER_STATUS,
  carriersQueryKey,
  outboundOrderQueryKey,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, InputNumber, Select, Space, Table } from 'antd';
import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchCarriers } from '@/api/carriers';
import { fetchOutboundOrder } from '@/api/outbound-orders';
import { createShipment } from '@/api/shipments';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function ShipmentFormPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const outboundOrderId = Number(params.get('outboundOrderId') || 0);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const outboundQuery = useQuery({
    queryKey: outboundOrderQueryKey(tenantId, outboundOrderId || null),
    queryFn: ({ signal }) => fetchOutboundOrder(outboundOrderId, signal),
    enabled: tenantId != null && outboundOrderId > 0,
  });
  const carriersQuery = useQuery({
    queryKey: carriersQueryKey(tenantId, { status: CARRIER_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchCarriers({ status: CARRIER_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });
  const rows = useMemo(
    () =>
      (outboundQuery.data?.items ?? []).filter((item) => item.remaining_shippable_quantity > 0),
    [outboundQuery.data],
  );
  const [carrierId, setCarrierId] = useState<number>();
  const [trackingNo, setTrackingNo] = useState('');
  const [remark, setRemark] = useState('');
  const [qty, setQty] = useState<Record<number, number>>({});
  const mutation = useMutation({
    mutationFn: () =>
      createShipment({
        outbound_order_id: outboundOrderId,
        carrier_id: carrierId ?? 0,
        tracking_no: trackingNo.trim() || null,
        remark: remark.trim() || null,
        items: rows
          .map((item) => ({
            outbound_order_item_id: item.id,
            quantity: qty[item.id] ?? item.remaining_shippable_quantity,
          }))
          .filter((item) => item.quantity > 0),
      }),
    onSuccess: async (created) => {
      message.success('已保存物流草稿。确认发货前不会改变库存和订单发货状态。');
      await queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'shipments'] });
      await queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'outbound-order'] });
      navigate(`/shipments/${created.id}`);
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });
  const outbound = outboundQuery.data;
  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '新建物流单'}
        description="本次数量默认等于剩余可发。保存草稿不会扣库存，也不会把订单改成已发货。"
        extra={
          <Space>
            <Button onClick={() => navigate(`/outbound-orders/${outboundOrderId}`)}>返回出库单</Button>
            <Button
              type="primary"
              loading={mutation.isPending}
              disabled={!carrierId || rows.length === 0}
              onClick={() => mutation.mutate()}
            >
              保存草稿
            </Button>
          </Space>
        }
      />
      <p>
        出库单 {outbound?.outbound_no} · 销售订单 {outbound?.sales_order_no} · {outbound?.customer_name}
      </p>
      <p>收件人 {outbound?.recipient_name || '-'} · {outbound?.address || '-'}</p>
      <div className="mb-4 flex max-w-xl flex-col gap-3">
        <div>
          <div className="mb-1 text-sm">物流商</div>
          <Select
            className="w-full"
            placeholder="选择启用中的物流商"
            value={carrierId}
            onChange={setCarrierId}
            options={(carriersQuery.data?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.name} (${item.code})`,
            }))}
          />
        </div>
        <div>
          <div className="mb-1 text-sm">运单号</div>
          <Input
            value={trackingNo}
            maxLength={64}
            placeholder="可稍后在草稿中填写，确认发货前必须有运单号"
            onChange={(event) => setTrackingNo(event.target.value)}
          />
        </div>
        <div>
          <div className="mb-1 text-sm">备注</div>
          <Input.TextArea
            rows={2}
            maxLength={255}
            value={remark}
            onChange={(event) => setRemark(event.target.value)}
          />
        </div>
      </div>
      <Table
        rowKey="id"
        pagination={false}
        dataSource={rows}
        locale={{ emptyText: '当前出库单没有剩余可发数量' }}
        columns={[
          { title: 'SKU', dataIndex: 'sku_code' },
          { title: '商品', dataIndex: 'product_name' },
          { title: '已出库', dataIndex: 'outbound_quantity' },
          { title: '此前已发', dataIndex: 'shipped_quantity' },
          { title: '剩余可发', dataIndex: 'remaining_shippable_quantity' },
          {
            title: '本次发货',
            render: (_, row) => (
              <InputNumber
                min={1}
                max={row.remaining_shippable_quantity}
                value={qty[row.id] ?? row.remaining_shippable_quantity}
                onChange={(value) =>
                  setQty((current) => ({ ...current, [row.id]: Number(value || 0) }))
                }
              />
            ),
          },
        ]}
      />
    </FormPageContainer>
  );
}
