import {
  ApiError,
  canApprovePurchaseOrder,
  canCancelPurchaseOrder,
  canEditPurchaseOrder,
  canRejectPurchaseOrder,
  canSubmitPurchaseOrder,
  formatPurchaseAmount,
  PERMISSION_CODE,
  PURCHASE_ORDER_STATUS,
  purchaseOrderQueryKey,
  purchaseOrderStatusLabel,
  specValuesLabel,
  type PurchaseOrderDetail,
  type PurchaseOrderItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Input, Space, Steps, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useParams } from 'react-router-dom';
import {
  approvePurchaseOrder,
  cancelPurchaseOrder,
  fetchPurchaseOrder,
  rejectPurchaseOrder,
  submitPurchaseOrder,
} from '@/api/purchase-orders';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDate, formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

function statusTag(status: string) {
  const color =
    status === PURCHASE_ORDER_STATUS.pendingApproval
      ? 'processing'
      : status === PURCHASE_ORDER_STATUS.waitingReceipt
        ? 'blue'
        : status === PURCHASE_ORDER_STATUS.rejected
          ? 'warning'
          : 'default';
  return <Tag color={color}>{purchaseOrderStatusLabel(status)}</Tag>;
}

function stepState(order: PurchaseOrderDetail) {
  if (order.status === PURCHASE_ORDER_STATUS.cancelled) {
    return { current: 0, status: 'error' as const };
  }
  if (order.status === PURCHASE_ORDER_STATUS.draft) {
    return { current: 0, status: 'process' as const };
  }
  if (order.status === PURCHASE_ORDER_STATUS.pendingApproval) {
    return { current: 1, status: 'process' as const };
  }
  if (order.status === PURCHASE_ORDER_STATUS.rejected) {
    return { current: 2, status: 'error' as const };
  }
  return { current: 3, status: 'finish' as const };
}

export function PurchaseDetailPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const params = useParams();
  const orderId = Number(params.id);
  const validId = Number.isInteger(orderId) && orderId > 0;

  const detailQuery = useQuery({
    queryKey: purchaseOrderQueryKey(tenantId, validId ? orderId : null),
    queryFn: ({ signal }) => fetchPurchaseOrder(orderId, signal),
    enabled: tenantId != null && validId,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-orders'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-order'] });
  };

  const submitMutation = useMutation({
    mutationFn: submitPurchaseOrder,
    onSuccess: () => {
      message.success('已提交审核');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '提交失败');
    },
  });

  const approveMutation = useMutation({
    mutationFn: approvePurchaseOrder,
    onSuccess: () => {
      message.success('审核通过，已进入待收货');
      invalidate();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '审核失败');
    },
  });

  const order = detailQuery.data;
  const steps = order ? stepState(order) : null;

  const columns: ColumnsType<PurchaseOrderItem> = [
    {
      title: 'SKU',
      dataIndex: 'sku_code',
      key: 'sku_code',
      width: 160,
      render: (value: string) => <CodeCell value={value} />,
    },
    {
      title: '商品',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 200,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '规格',
      key: 'spec',
      width: 160,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    { title: '采购数量', dataIndex: 'quantity', key: 'quantity', width: 100 },
    { title: '已收数量', dataIndex: 'received_quantity', key: 'received_quantity', width: 100 },
    {
      title: '单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 110,
      render: (value: number | null) => formatPurchaseAmount(value),
    },
    {
      title: '金额',
      dataIndex: 'line_amount',
      key: 'line_amount',
      width: 110,
      render: (value: number | null) => formatPurchaseAmount(value),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '采购单详情'}
        description={props.description ?? '审核通过只进入待收货，不会增加库存。'}
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/purchases')}>返回列表</Button>
            {order && canEditPurchaseOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseUpdate}>
                <Button onClick={() => navigate(`/purchases/${order.id}/edit`)}>编辑</Button>
              </Can>
            ) : null}
            {order && canSubmitPurchaseOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseSubmit}>
                <Button type="primary" loading={submitMutation.isPending} onClick={() => submitMutation.mutate(order.id)}>
                  {order.status === PURCHASE_ORDER_STATUS.rejected ? '重新提交' : '提交审核'}
                </Button>
              </Can>
            ) : null}
            {order && canApprovePurchaseOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseAudit}>
                <Button type="primary" loading={approveMutation.isPending} onClick={() => approveMutation.mutate(order.id)}>
                  审核通过
                </Button>
              </Can>
            ) : null}
            {order && canRejectPurchaseOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseAudit}>
                <Button
                  onClick={() => {
                    let reason = '';
                    modal.confirm({
                      title: '驳回采购单',
                      content: (
                        <Input.TextArea
                          rows={3}
                          maxLength={255}
                          placeholder="请填写驳回原因"
                          onChange={(event) => {
                            reason = event.target.value;
                          }}
                        />
                      ),
                      onOk: async () => {
                        const text = reason.trim();
                        if (!text) {
                          message.error('请填写驳回原因');
                          return Promise.reject();
                        }
                        try {
                          await rejectPurchaseOrder(order.id, text);
                          message.success('已驳回');
                          invalidate();
                        } catch (error) {
                          message.error(error instanceof ApiError ? error.message : '驳回失败');
                          return Promise.reject();
                        }
                      },
                    });
                  }}
                >
                  驳回
                </Button>
              </Can>
            ) : null}
            {order && canCancelPurchaseOrder(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseCancel}>
                <Button
                  danger
                  onClick={() => {
                    let reason = '';
                    modal.confirm({
                      title: '取消采购单',
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
                          await cancelPurchaseOrder(order.id, reason.trim() || null);
                          message.success('已取消');
                          invalidate();
                        } catch (error) {
                          message.error(error instanceof ApiError ? error.message : '取消失败');
                          return Promise.reject();
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
            <Steps
              className="mb-6"
              current={steps?.current}
              status={steps?.status}
              items={[
                { title: '创建' },
                { title: '提交审核' },
                { title: order.status === PURCHASE_ORDER_STATUS.rejected ? '已驳回' : '审核' },
                { title: '待收货' },
              ]}
            />
            <Descriptions column={2} size="small" className='mt-4!'>
              <Descriptions.Item label="采购单号">{order.order_no}</Descriptions.Item>
              <Descriptions.Item label="状态">{statusTag(order.status)}</Descriptions.Item>
              <Descriptions.Item label="供应商">{order.supplier_name}</Descriptions.Item>
              <Descriptions.Item label="仓库">{order.warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="预计到货">{formatDate(order.expected_arrival_date)}</Descriptions.Item>
              <Descriptions.Item label="创建人">{order.created_by_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="提交时间">{formatDateTime(order.submitted_at)}</Descriptions.Item>
              <Descriptions.Item label="审核人">{order.approved_by_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="驳回原因">{order.reject_reason || '-'}</Descriptions.Item>
              <Descriptions.Item label="取消原因">{order.cancel_reason || '-'}</Descriptions.Item>
              <Descriptions.Item label="备注">{order.remark || '-'}</Descriptions.Item>
              <Descriptions.Item label="金额">{formatPurchaseAmount(order.total_amount)}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="采购明细" className="mt-4!">
            <AppTable
              rowKey="id"
              size="small"
              columns={columns}
              dataSource={order.items}
              pagination={false}
              fillHeight={false}
            />
          </Card>
        </>
      ) : null}
    </FormPageContainer>
  );
}
