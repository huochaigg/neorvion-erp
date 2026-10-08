import { ApiError, purchaseOrderQueryKey, purchaseReceiptsQueryKey } from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, InputNumber, Space, Table } from 'antd';
import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createPurchaseReceipt } from '@/api/purchase-receipts';
import { fetchPurchaseOrder } from '@/api/purchase-orders';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function PurchaseReceiptFormPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const purchaseOrderId = Number(params.get('purchaseOrderId') || 0);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const orderQuery = useQuery({
    queryKey: purchaseOrderQueryKey(tenantId, purchaseOrderId || null),
    queryFn: ({ signal }) => fetchPurchaseOrder(purchaseOrderId, signal),
    enabled: tenantId != null && purchaseOrderId > 0,
  });
  const rows = useMemo(
    () =>
      (orderQuery.data?.items ?? [])
        .map((item) => ({
          ...item,
          remaining: item.quantity - item.received_quantity,
        }))
        .filter((item) => item.remaining > 0),
    [orderQuery.data],
  );
  const [qty, setQty] = useState<Record<number, number>>({});
  const mutation = useMutation({
    mutationFn: () =>
      createPurchaseReceipt({
        purchase_order_id: purchaseOrderId,
        items: rows
          .map((item) => ({
            purchase_order_item_id: item.id,
            received_quantity: qty[item.id] ?? item.remaining,
          }))
          .filter((item) => item.received_quantity > 0),
      }),
    onSuccess: async (created) => {
      message.success('已保存收货草稿，尚未入库');
      await queryClient.invalidateQueries({ queryKey: purchaseReceiptsQueryKey(tenantId) });
      navigate(`/purchase-receipts/${created.id}`);
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });
  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '新建收货单'}
        description="本次数量默认等于剩余待收。保存草稿不会增加库存。"
        extra={
          <Space>
            <Button onClick={() => navigate(`/purchases/${purchaseOrderId}`)}>返回采购单</Button>
            <Button type="primary" loading={mutation.isPending} onClick={() => mutation.mutate()}>
              保存草稿
            </Button>
          </Space>
        }
      />
      <p>
        采购单 {orderQuery.data?.order_no} · {orderQuery.data?.supplier_name} ·{' '}
        {orderQuery.data?.warehouse_name}
      </p>
      <Table
        rowKey="id"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: 'SKU', dataIndex: 'sku_code' },
          { title: '商品', dataIndex: 'product_name' },
          { title: '采购数量', dataIndex: 'quantity' },
          { title: '累计已收', dataIndex: 'received_quantity' },
          { title: '剩余待收', dataIndex: 'remaining' },
          {
            title: '本次收货',
            render: (_, row) => (
              <InputNumber
                min={1}
                max={row.remaining}
                value={qty[row.id] ?? row.remaining}
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
