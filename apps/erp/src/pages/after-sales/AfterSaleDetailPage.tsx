import {
  AFTER_SALE_TYPE,
  afterSaleQueryKey,
  afterSaleRefundStatusLabel,
  afterSaleStatusLabel,
  afterSaleTypeLabel,
  ApiError,
  canApproveAfterSale,
  canCancelAfterSale,
  canCreateRefund,
  canRejectAfterSale,
  formatSalesAmount,
  PERMISSION_CODE,
  refundRecordStatusLabel,
  refundsQueryKey,
  specValuesLabel,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type AfterSaleItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Input, InputNumber, Modal, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  approveAfterSale,
  cancelAfterSale,
  createAfterSaleRefund,
  fetchAfterSale,
  rejectAfterSale,
} from '@/api/after-sales';
import { confirmRefund, failRefund, fetchRefunds } from '@/api/refunds';
import { fetchWarehouses } from '@/api/warehouses';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

interface ApproveDraft {
  approved_return_quantity: number;
  approved_refund_amount: number;
}

export function AfterSaleDetailPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const afterSaleId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const [approveOpen, setApproveOpen] = useState(false);
  const [warehouseId, setWarehouseId] = useState<number>();
  const [approveDraft, setApproveDraft] = useState<Record<number, ApproveDraft>>({});
  const [refundOpen, setRefundOpen] = useState(false);
  const [refundAmount, setRefundAmount] = useState<number>(0);
  const [refundExternal, setRefundExternal] = useState('');

  const query = useQuery({
    queryKey: afterSaleQueryKey(tenantId, afterSaleId),
    queryFn: ({ signal }) => fetchAfterSale(afterSaleId, signal),
    enabled: tenantId != null && afterSaleId > 0,
  });
  const order = query.data;
  const refundQuery = useQuery({
    queryKey: refundsQueryKey(tenantId, { afterSaleId, page: 1, pageSize: 50 }),
    queryFn: ({ signal }) => fetchRefunds({ afterSaleId, page: 1, pageSize: 50 }, signal),
    enabled: tenantId != null && afterSaleId > 0,
  });
  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null && approveOpen,
  });

  const remainingRefund = useMemo(() => {
    if (!order) {
      return 0;
    }
    const approved = order.approved_refund_amount ?? order.requested_refund_amount;
    const used = (refundQuery.data?.items ?? [])
      .filter((row) => row.status === 'SUCCESS' || row.status === 'PENDING')
      .reduce((sum, row) => sum + row.amount, 0);
    return Math.max(Number((approved - used).toFixed(2)), 0);
  }, [order, refundQuery.data]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sales'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sale'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sale-preview'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'return-orders'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'return-order'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'refunds'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-order'] });
  };

  const approveMutation = useMutation({
    mutationFn: () =>
      approveAfterSale(afterSaleId, {
        warehouse_id: warehouseId,
        items: (order?.items ?? []).map((item) => ({
          item_id: item.id,
          approved_return_quantity: approveDraft[item.id]?.approved_return_quantity ?? item.return_quantity,
          approved_refund_amount: approveDraft[item.id]?.approved_refund_amount ?? item.requested_refund_amount,
        })),
      }),
    onSuccess: () => {
      message.success('已审核通过');
      setApproveOpen(false);
      invalidate();
    },
    onError: (error: unknown) => message.error(error instanceof ApiError ? error.message : '审核失败'),
  });

  const columns: ColumnsType<AfterSaleItem> = [
    { title: '商品', dataIndex: 'product_name', width: 160, render: (value: string) => <EllipsisCell value={value} /> },
    { title: 'SKU', dataIndex: 'sku_code', width: 140, render: (value: string) => <CodeCell value={value} /> },
    {
      title: '规格',
      key: 'spec',
      width: 140,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    { title: '购买数量', dataIndex: 'original_quantity', width: 90 },
    { title: '已出库', dataIndex: 'outbound_quantity', width: 80 },
    { title: '申请退货', dataIndex: 'return_quantity', width: 90 },
    {
      title: '批准退货',
      dataIndex: 'approved_return_quantity',
      width: 90,
      render: (value: number | null) => value ?? '-',
    },
    {
      title: '申请退款',
      dataIndex: 'requested_refund_amount',
      width: 110,
      render: (value: number) => formatSalesAmount(value),
    },
    {
      title: '批准退款',
      dataIndex: 'approved_refund_amount',
      width: 110,
      render: (value: number | null) => formatSalesAmount(value),
    },
  ];

  const openApprove = () => {
    if (!order) {
      return;
    }
    const next: Record<number, ApproveDraft> = {};
    for (const item of order.items) {
      next[item.id] = {
        approved_return_quantity: item.return_quantity,
        approved_refund_amount: item.requested_refund_amount,
      };
    }
    setApproveDraft(next);
    setApproveOpen(true);
  };

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '售后单详情'}
        description={props.description}
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/after-sales')}>返回列表</Button>
            {order ? (
              <Button onClick={() => navigate(`/orders/${order.sales_order_id}`)}>原销售订单</Button>
            ) : null}
            {order?.return_order_id ? (
              <Button onClick={() => navigate(`/return-orders/${order.return_order_id}`)}>退货单</Button>
            ) : null}
            {order && canApproveAfterSale(order.status) ? (
              <Can permission={PERMISSION_CODE.afterSaleApprove}>
                <Button type="primary" onClick={openApprove}>
                  审核通过
                </Button>
              </Can>
            ) : null}
            {order && canRejectAfterSale(order.status) ? (
              <Can permission={PERMISSION_CODE.afterSaleReject}>
                <Button
                  danger
                  onClick={() => {
                    let reason = '';
                    modal.confirm({
                      title: '拒绝售后',
                      content: (
                        <Input.TextArea
                          rows={3}
                          maxLength={255}
                          placeholder="拒绝原因"
                          onChange={(event) => {
                            reason = event.target.value;
                          }}
                        />
                      ),
                      onOk: async () => {
                        if (!reason.trim()) {
                          message.error('请填写拒绝原因');
                          return Promise.reject(new Error('reason required'));
                        }
                        try {
                          await rejectAfterSale(afterSaleId, { reason: reason.trim() });
                          message.success('已拒绝，可退数量已释放');
                          invalidate();
                        } catch (error) {
                          message.error(error instanceof ApiError ? error.message : '拒绝失败');
                          return Promise.reject(new Error('reject failed'));
                        }
                      },
                    });
                  }}
                >
                  拒绝
                </Button>
              </Can>
            ) : null}
            {order && canCancelAfterSale(order.status) ? (
              <Can permission={PERMISSION_CODE.afterSaleCancel}>
                <Button
                  onClick={() => {
                    modal.confirm({
                      title: '取消售后申请？',
                      onOk: async () => {
                        try {
                          await cancelAfterSale(afterSaleId);
                          message.success('已取消');
                          invalidate();
                        } catch (error) {
                          message.error(error instanceof ApiError ? error.message : '取消失败');
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
            {order && canCreateRefund(order.status, order.type) ? (
              <Can permission={PERMISSION_CODE.refundCreate}>
                <Button
                  type="primary"
                  onClick={() => {
                    setRefundAmount(remainingRefund);
                    setRefundExternal('');
                    setRefundOpen(true);
                  }}
                >
                  确认退款
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {order ? (
        <>
          <Card className="mb-4">
            <Descriptions column={2} size="small">
              <Descriptions.Item label="售后单号">{order.after_sale_no}</Descriptions.Item>
              <Descriptions.Item label="类型">{afterSaleTypeLabel(order.type)}</Descriptions.Item>
              <Descriptions.Item label="售后状态">
                <Tag>{afterSaleStatusLabel(order.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="退款状态">{afterSaleRefundStatusLabel(order.refund_status)}</Descriptions.Item>
              <Descriptions.Item label="销售订单">{order.sales_order_no}</Descriptions.Item>
              <Descriptions.Item label="客户">{order.customer_name}</Descriptions.Item>
              <Descriptions.Item label="币种">{order.currency_code}</Descriptions.Item>
              <Descriptions.Item label="申请退款">{formatSalesAmount(order.requested_refund_amount)}</Descriptions.Item>
              <Descriptions.Item label="批准退款">{formatSalesAmount(order.approved_refund_amount)}</Descriptions.Item>
              <Descriptions.Item label="申请原因" span={2}>
                {order.reason}
              </Descriptions.Item>
              <Descriptions.Item label="拒绝原因" span={2}>
                {order.reject_reason || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="申请人">{order.requested_by_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="申请时间">{formatDateTime(order.created_at)}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="售后明细" className="mb-4">
            <AppTable rowKey="id" size="small" columns={columns} dataSource={order.items} pagination={false} fillHeight={false} />
          </Card>
          <Card title="退款记录">
            <AppTable
              rowKey="id"
              size="small"
              pagination={false}
              fillHeight={false}
              dataSource={refundQuery.data?.items ?? []}
              locale={{ emptyText: order.type === AFTER_SALE_TYPE.returnOnly ? '仅退货不产生退款' : '还没有退款记录' }}
              columns={[
                { title: '退款编号', dataIndex: 'refund_no', width: 160 },
                {
                  title: '金额',
                  dataIndex: 'amount',
                  width: 110,
                  render: (value: number) => formatSalesAmount(value),
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 100,
                  render: (value: string) => refundRecordStatusLabel(value),
                },
                {
                  title: '外部流水号',
                  dataIndex: 'external_reference_no',
                  width: 160,
                  render: (value: string | null) => value || '-',
                },
                {
                  title: '失败原因',
                  dataIndex: 'failure_reason',
                  width: 180,
                  render: (value: string | null) => value || '-',
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 140,
                  render: (_, row) =>
                    row.status === 'PENDING' ? (
                      <Can permission={PERMISSION_CODE.refundConfirm}>
                        <Space>
                          <Button
                            type="link"
                            onClick={async () => {
                              try {
                                await confirmRefund(row.id, {});
                                message.success('已确认退款成功');
                                invalidate();
                              } catch (error) {
                                message.error(error instanceof ApiError ? error.message : '确认失败');
                              }
                            }}
                          >
                            成功
                          </Button>
                          <Button
                            type="link"
                            danger
                            onClick={() => {
                              let reason = '';
                              modal.confirm({
                                title: '标记退款失败',
                                content: (
                                  <Input.TextArea
                                    rows={3}
                                    placeholder="失败原因"
                                    onChange={(event) => {
                                      reason = event.target.value;
                                    }}
                                  />
                                ),
                                onOk: async () => {
                                  if (!reason.trim()) {
                                    message.error('请填写失败原因');
                                    return Promise.reject(new Error('reason required'));
                                  }
                                  await failRefund(row.id, { failure_reason: reason.trim() });
                                  message.success('已标记失败');
                                  invalidate();
                                },
                              });
                            }}
                          >
                            失败
                          </Button>
                        </Space>
                      </Can>
                    ) : null,
                },
              ]}
            />
          </Card>
        </>
      ) : null}
      <Modal
        title="审核通过"
        open={approveOpen}
        onCancel={() => setApproveOpen(false)}
        onOk={() => approveMutation.mutate()}
        confirmLoading={approveMutation.isPending}
        width={760}
      >
        {order?.type !== AFTER_SALE_TYPE.refundOnly ? (
          <Select
            className="mb-3"
            style={{ width: '100%' }}
            placeholder="退货仓库，不选则使用原履约仓"
            allowClear
            value={warehouseId}
            onChange={setWarehouseId}
            options={(warehouseQuery.data?.items ?? []).map((item) => ({
              value: item.id,
              label: item.name,
            }))}
          />
        ) : null}
        <AppTable
          rowKey="id"
          size="small"
          pagination={false}
          fillHeight={false}
          dataSource={order?.items ?? []}
          columns={[
            { title: 'SKU', dataIndex: 'sku_code', width: 140 },
            { title: '申请退货', dataIndex: 'return_quantity', width: 90 },
            {
              title: '批准退货',
              key: 'approved_return_quantity',
              width: 120,
              render: (_, record) => (
                <InputNumber
                  min={0}
                  max={record.return_quantity}
                  value={approveDraft[record.id]?.approved_return_quantity}
                  onChange={(value) => {
                    setApproveDraft((prev) => ({
                      ...prev,
                      [record.id]: {
                        ...prev[record.id],
                        approved_return_quantity: Number(value ?? 0),
                      },
                    }));
                  }}
                />
              ),
            },
            {
              title: '申请退款',
              dataIndex: 'requested_refund_amount',
              width: 100,
              render: (value: number) => formatSalesAmount(value),
            },
            {
              title: '批准退款',
              key: 'approved_refund_amount',
              width: 130,
              render: (_, record) => (
                <InputNumber
                  min={0}
                  max={record.requested_refund_amount}
                  precision={2}
                  value={approveDraft[record.id]?.approved_refund_amount}
                  onChange={(value) => {
                    setApproveDraft((prev) => ({
                      ...prev,
                      [record.id]: {
                        ...prev[record.id],
                        approved_refund_amount: Number(value ?? 0),
                      },
                    }));
                  }}
                />
              ),
            },
          ]}
        />
      </Modal>
      <Modal
        title="确认退款"
        open={refundOpen}
        onCancel={() => setRefundOpen(false)}
        onOk={async () => {
          try {
            const created = await createAfterSaleRefund(afterSaleId, {
              amount: refundAmount,
              external_reference_no: refundExternal.trim() || null,
            });
            await confirmRefund(created.id, { external_reference_no: refundExternal.trim() || null });
            message.success('已确认退款成功');
            setRefundOpen(false);
            invalidate();
          } catch (error) {
            message.error(error instanceof ApiError ? error.message : '退款失败');
          }
        }}
      >
        <p className="mb-2 text-sm text-slate-600">剩余可退 {formatSalesAmount(remainingRefund)}。本版只做 ERP 内人工确认，不调用支付渠道。</p>
        <InputNumber
          className="mb-3 w-full"
          min={0}
          max={remainingRefund}
          precision={2}
          value={refundAmount}
          onChange={(value) => setRefundAmount(Number(value ?? 0))}
        />
        <Input
          placeholder="外部退款流水号（可选）"
          value={refundExternal}
          onChange={(event) => setRefundExternal(event.target.value)}
        />
      </Modal>
    </FormPageContainer>
  );
}
