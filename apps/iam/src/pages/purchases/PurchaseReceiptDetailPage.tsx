import {
  ApiError,
  inventoryQueryKey,
  inventoryTransactionsQueryKey,
  PERMISSION_CODE,
  purchaseOrderQueryKey,
  purchaseOrdersQueryKey,
  purchaseReceiptQueryKey,
  purchaseReceiptsQueryKey,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Descriptions, Popconfirm, Space, Table, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { cancelPurchaseReceipt, confirmPurchaseReceipt, fetchPurchaseReceipt } from '@/api/purchase-receipts';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

const STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  CONFIRMED: '已确认',
  CANCELLED: '已作废',
};

export function PurchaseReceiptDetailPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const receiptId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: purchaseReceiptQueryKey(tenantId, receiptId),
    queryFn: ({ signal }) => fetchPurchaseReceipt(receiptId, signal),
    enabled: tenantId != null && receiptId > 0,
  });
  const receipt = query.data;

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: purchaseReceiptQueryKey(tenantId, receiptId) });
    await queryClient.invalidateQueries({ queryKey: purchaseReceiptsQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: purchaseOrdersQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: purchaseOrderQueryKey(tenantId, receipt?.purchase_order_id ?? null) });
    await queryClient.invalidateQueries({ queryKey: inventoryQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: inventoryTransactionsQueryKey(tenantId) });
  }

  const confirmMutation = useMutation({
    mutationFn: () => confirmPurchaseReceipt(receiptId),
    onSuccess: async () => {
      message.success('已入库，实际库存已增加，预占不变');
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '确认失败');
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelPurchaseReceipt(receiptId),
    onSuccess: async () => {
      message.success('已作废草稿');
      await refresh();
    },
  });

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? receipt?.receipt_no ?? '收货单'}
        extra={
          <Space>
            <Button onClick={() => navigate('/purchase-receipts')}>返回列表</Button>
            {receipt?.status === 'DRAFT' ? (
              <>
                <Can permission={PERMISSION_CODE.purchaseReceiptConfirm}>
                  <Popconfirm title="确认后将增加库存，是否继续？" onConfirm={() => confirmMutation.mutate()}>
                    <Button type="primary" loading={confirmMutation.isPending}>
                      确认收货
                    </Button>
                  </Popconfirm>
                </Can>
                <Can permission={PERMISSION_CODE.purchaseReceiptCancel}>
                  <Button danger loading={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
                    作废
                  </Button>
                </Can>
              </>
            ) : null}
          </Space>
        }
      />
      {receipt ? (
        <>
          <Descriptions column={3}>
            <Descriptions.Item label="采购单">{receipt.purchase_order_no}</Descriptions.Item>
            <Descriptions.Item label="供应商">{receipt.supplier_name}</Descriptions.Item>
            <Descriptions.Item label="仓库">{receipt.warehouse_name}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag>{STATUS_LABEL[receipt.status] ?? receipt.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="收货人">{receipt.received_by_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="收货时间">{formatDateTime(receipt.received_at)}</Descriptions.Item>
          </Descriptions>
          <Table
            rowKey="id"
            pagination={false}
            dataSource={receipt.items}
            className="mt-4"
            columns={[
              { title: 'SKU', dataIndex: 'sku_code' },
              { title: '商品', dataIndex: 'product_name' },
              { title: '采购数量', dataIndex: 'order_quantity' },
              { title: '此前已收', dataIndex: 'received_before' },
              { title: '本次收货', dataIndex: 'received_quantity' },
            ]}
          />
        </>
      ) : null}
    </FormPageContainer>
  );
}
