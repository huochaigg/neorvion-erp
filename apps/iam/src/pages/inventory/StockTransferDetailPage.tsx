import {
  ApiError,
  canCancelStockTransfer,
  canConfirmTransferOutbound,
  canConfirmTransferReceive,
  canEditStockTransfer,
  canSubmitStockTransfer,
  inventoryQueryKey,
  inventoryTransactionsQueryKey,
  PERMISSION_CODE,
  specValuesLabel,
  stockTransferQueryKey,
  stockTransfersQueryKey,
  stockTransferStatusLabel,
  transferStepIndex,
  type StockTransferItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Descriptions, Popconfirm, Space, Steps, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useParams } from 'react-router-dom';
import {
  cancelStockTransfer,
  confirmTransferOutbound,
  confirmTransferReceive,
  fetchStockTransfer,
  submitStockTransfer,
} from '@/api/stock-transfers';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

function itemStatus(orderStatus: string): string {
  if (orderStatus === 'COMPLETED') {
    return '已收货';
  }
  if (orderStatus === 'IN_TRANSIT') {
    return '在途';
  }
  if (orderStatus === 'PENDING_OUTBOUND') {
    return '待调出';
  }
  if (orderStatus === 'CANCELLED') {
    return '已取消';
  }
  return '草稿';
}

export function StockTransferDetailPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const transferId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: stockTransferQueryKey(tenantId, transferId),
    queryFn: ({ signal }) => fetchStockTransfer(transferId, signal),
    enabled: tenantId != null && transferId > 0,
  });
  const transfer = query.data;

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: stockTransferQueryKey(tenantId, transferId) });
    await queryClient.invalidateQueries({ queryKey: stockTransfersQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: inventoryQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: inventoryTransactionsQueryKey(tenantId) });
  }

  const submitMutation = useMutation({
    mutationFn: () => submitStockTransfer(transferId),
    onSuccess: async () => {
      message.success('已提交，待确认调出');
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '提交失败');
    },
  });
  const outboundMutation = useMutation({
    mutationFn: () => confirmTransferOutbound(transferId),
    onSuccess: async () => {
      message.success('已从调出仓扣减库存，进入在途');
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '确认调出失败');
    },
  });
  const receiveMutation = useMutation({
    mutationFn: () => confirmTransferReceive(transferId),
    onSuccess: async () => {
      message.success('已增加到目标仓库存');
      await refresh();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '确认调入失败');
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelStockTransfer(transferId),
    onSuccess: async () => {
      message.success('调拨单已取消');
      await refresh();
    },
  });

  const columns: ColumnsType<StockTransferItem> = [
    { title: 'SKU', dataIndex: 'sku_code', width: 140 },
    { title: '商品', dataIndex: 'product_name', width: 160 },
    {
      title: '规格',
      key: 'spec',
      width: 140,
      render: (_, row) => specValuesLabel(row.spec_values),
    },
    { title: '计划调拨', dataIndex: 'quantity', width: 100 },
    { title: '已调出', dataIndex: 'outbound_quantity', width: 90 },
    { title: '已收货', dataIndex: 'received_quantity', width: 90 },
    {
      title: '调出仓可用',
      dataIndex: 'source_available_quantity',
      width: 110,
      render: (value: number | null) => (value == null ? '未建库存' : value),
    },
    {
      title: '当前状态',
      key: 'line_status',
      width: 100,
      render: () => itemStatus(transfer?.status ?? ''),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? transfer?.transfer_no ?? '调拨详情'}
        extra={
          <Space>
            <Button onClick={() => navigate('/stock-transfers')}>返回列表</Button>
            {transfer && canEditStockTransfer(transfer.status) ? (
              <Can permission={PERMISSION_CODE.stockTransferUpdate}>
                <Button onClick={() => navigate(`/stock-transfers/${transfer.id}/edit`)}>编辑</Button>
              </Can>
            ) : null}
            {transfer && canSubmitStockTransfer(transfer.status, transfer.items.length > 0) ? (
              <Can permission={PERMISSION_CODE.stockTransferSubmit}>
                <Button type="primary" loading={submitMutation.isPending} onClick={() => submitMutation.mutate()}>
                  提交
                </Button>
              </Can>
            ) : null}
            {transfer && canConfirmTransferOutbound(transfer.status) ? (
              <Can permission={PERMISSION_CODE.stockTransferOutbound}>
                <Popconfirm
                  title="确认后库存将从调出仓正式减少并进入在途状态。"
                  onConfirm={() => outboundMutation.mutate()}
                >
                  <Button type="primary" loading={outboundMutation.isPending}>
                    确认调出
                  </Button>
                </Popconfirm>
              </Can>
            ) : null}
            {transfer && canConfirmTransferReceive(transfer.status) ? (
              <Can permission={PERMISSION_CODE.stockTransferReceive}>
                <Popconfirm title="确认后商品将增加到目标仓库存。" onConfirm={() => receiveMutation.mutate()}>
                  <Button type="primary" loading={receiveMutation.isPending}>
                    确认调入
                  </Button>
                </Popconfirm>
              </Can>
            ) : null}
            {transfer && canCancelStockTransfer(transfer.status) ? (
              <Can permission={PERMISSION_CODE.stockTransferCancel}>
                <Button danger loading={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
                  取消
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {transfer ? (
        <>
          <Steps
            className="mb-4 max-w-3xl"
            current={transferStepIndex(transfer.status)}
            items={[
              { title: '创建' },
              { title: '待调出' },
              { title: '运输中' },
              { title: '已完成' },
            ]}
          />
          <Descriptions column={3} className="mb-4">
            <Descriptions.Item label="调拨单号">{transfer.transfer_no}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag>{stockTransferStatusLabel(transfer.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="调出仓">{transfer.source_warehouse_name}</Descriptions.Item>
            <Descriptions.Item label="调入仓">{transfer.target_warehouse_name}</Descriptions.Item>
            <Descriptions.Item label="创建人">{transfer.created_by_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatDateTime(transfer.created_at)}</Descriptions.Item>
            <Descriptions.Item label="提交时间">{formatDateTime(transfer.submitted_at)}</Descriptions.Item>
            <Descriptions.Item label="调出时间">{formatDateTime(transfer.outbound_at)}</Descriptions.Item>
            <Descriptions.Item label="收货时间">{formatDateTime(transfer.received_at)}</Descriptions.Item>
          </Descriptions>
          <AppTable rowKey="id" columns={columns} dataSource={transfer.items} pagination={false} />
        </>
      ) : null}
    </FormPageContainer>
  );
}
