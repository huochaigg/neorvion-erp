import {
  ApiError,
  canApprovePurchaseReturn,
  canCancelPurchaseReturn,
  canCreatePurchaseReturnOutbound,
  canCreateSupplierRefund,
  canRejectPurchaseReturn,
  canSubmitPurchaseReturn,
  defaultOutboundQuantity,
  formatPurchaseAmount,
  PERMISSION_CODE,
  purchaseReturnQueryKey,
  purchaseReturnRefundStatusLabel,
  purchaseReturnSettlementLabel,
  purchaseReturnStatusLabel,
  specValuesLabel,
  type PurchaseReturnItem,
} from '@neorvion/shared';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Descriptions, Input, InputNumber, Modal, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { confirmPurchaseReturnOutbound } from '@/api/purchase-return-outbounds';
import {
  approvePurchaseReturn,
  cancelPurchaseReturn,
  createPurchaseReturnOutbound,
  createPurchaseReturnRefund,
  fetchPurchaseReturn,
  rejectPurchaseReturn,
  submitPurchaseReturn,
} from '@/api/purchase-returns';
import { confirmSupplierRefund, failSupplierRefund } from '@/api/supplier-refunds';
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

export function PurchaseReturnDetailPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const returnId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const [approveOpen, setApproveOpen] = useState(false);
  const [approveDraft, setApproveDraft] = useState<Record<number, ApproveDraft>>({});
  const [outboundOpen, setOutboundOpen] = useState(false);
  const [outboundQty, setOutboundQty] = useState<Record<number, number>>({});
  const [refundOpen, setRefundOpen] = useState(false);
  const [refundAmount, setRefundAmount] = useState(0);
  const [refundExternal, setRefundExternal] = useState('');

  const query = useQuery({
    queryKey: purchaseReturnQueryKey(tenantId, returnId),
    queryFn: ({ signal }) => fetchPurchaseReturn(returnId, signal),
    enabled: tenantId != null && returnId > 0,
  });
  const order = query.data;

  const remainingRefund = useMemo(() => {
    if (!order) {
      return 0;
    }
    const approved = order.approved_refund_amount ?? order.requested_refund_amount;
    const used = (order.refunds ?? [])
      .filter((row) => row.status === 'SUCCESS' || row.status === 'PENDING')
      .reduce((sum, row) => sum + row.amount, 0);
    return Math.max(Number((approved - used).toFixed(2)), 0);
  }, [order]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-returns'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-return'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-return-preview'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-return-outbounds'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'supplier-refunds'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-order'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory-transactions'] });
  };

  const columns: ColumnsType<PurchaseReturnItem> = [
    { title: '商品', dataIndex: 'product_name', width: 150, render: (value: string) => <EllipsisCell value={value} /> },
    { title: 'SKU', dataIndex: 'sku_code', width: 130, render: (value: string) => <CodeCell value={value} /> },
    {
      title: '规格',
      key: 'spec',
      width: 120,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    { title: '原采购数量', dataIndex: 'original_ordered_quantity', width: 110 },
    { title: '累计收货', dataIndex: 'original_received_quantity', width: 90 },
    { title: '申请退货', dataIndex: 'requested_return_quantity', width: 90 },
    {
      title: '批准退货',
      dataIndex: 'approved_return_quantity',
      width: 90,
      render: (value: number | null) => value ?? '-',
    },
    { title: '累计已出库', dataIndex: 'returned_quantity', width: 100 },
    { title: '剩余待退', dataIndex: 'remaining_return_quantity', width: 90 },
    {
      title: '申请退款',
      dataIndex: 'requested_refund_amount',
      width: 110,
      render: (value: number | null) => formatPurchaseAmount(value),
    },
    {
      title: '批准退款',
      dataIndex: 'approved_refund_amount',
      width: 110,
      render: (value: number | null) => formatPurchaseAmount(value),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '采购退货详情'}
        description={props.description}
        extra={
          <Space wrap>
            <Button onClick={() => navigate('/purchase-returns')}>返回列表</Button>
            {order ? (
              <Button onClick={() => navigate(`/purchases/${order.purchase_order_id}`)}>原采购单</Button>
            ) : null}
            {order && canSubmitPurchaseReturn(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseReturnSubmit}>
                <Button
                  type="primary"
                  onClick={() => {
                    submitPurchaseReturn(returnId)
                      .then(() => {
                        message.success('已提交审核');
                        invalidate();
                      })
                      .catch((error: unknown) =>
                        message.error(error instanceof ApiError ? error.message : '提交失败'),
                      );
                  }}
                >
                  提交审核
                </Button>
              </Can>
            ) : null}
            {order && canApprovePurchaseReturn(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseReturnApprove}>
                <Button
                  type="primary"
                  onClick={() => {
                    const next: Record<number, ApproveDraft> = {};
                    for (const item of order.items) {
                      next[item.id] = {
                        approved_return_quantity: item.requested_return_quantity,
                        approved_refund_amount: item.requested_refund_amount ?? 0,
                      };
                    }
                    setApproveDraft(next);
                    setApproveOpen(true);
                  }}
                >
                  审核通过
                </Button>
              </Can>
            ) : null}
            {order && canRejectPurchaseReturn(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseReturnReject}>
                <Button
                  onClick={() => {
                    let reason = '';
                    modal.confirm({
                      title: '驳回采购退货',
                      content: (
                        <Input.TextArea
                          rows={3}
                          placeholder="拒绝原因"
                          onChange={(event) => {
                            reason = event.target.value;
                          }}
                        />
                      ),
                      onOk: async () => {
                        if (!reason.trim()) {
                          message.error('请填写拒绝原因');
                          return Promise.reject();
                        }
                        await rejectPurchaseReturn(returnId, { reason: reason.trim() });
                        message.success('已拒绝');
                        invalidate();
                      },
                    });
                  }}
                >
                  驳回
                </Button>
              </Can>
            ) : null}
            {order && canCancelPurchaseReturn(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseReturnCancel}>
                <Button
                  danger
                  onClick={() => {
                    cancelPurchaseReturn(returnId)
                      .then(() => {
                        message.success('已取消');
                        invalidate();
                      })
                      .catch((error: unknown) =>
                        message.error(error instanceof ApiError ? error.message : '取消失败'),
                      );
                  }}
                >
                  取消
                </Button>
              </Can>
            ) : null}
            {order && canCreatePurchaseReturnOutbound(order.status) ? (
              <Can permission={PERMISSION_CODE.purchaseReturnOutbound}>
                <Button
                  type="primary"
                  onClick={() => {
                    const next: Record<number, number> = {};
                    for (const item of order.items) {
                      next[item.id] = defaultOutboundQuantity(
                        item.remaining_return_quantity,
                        item.inventory_available,
                      );
                    }
                    setOutboundQty(next);
                    setOutboundOpen(true);
                  }}
                >
                  创建退货出库单
                </Button>
              </Can>
            ) : null}
            {order && canCreateSupplierRefund(order.status, order.settlement_type) ? (
              <Can permission={PERMISSION_CODE.supplierRefundCreate}>
                <Button
                  onClick={() => {
                    setRefundAmount(remainingRefund);
                    setRefundOpen(true);
                  }}
                >
                  登记供应商退款
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
              <Descriptions.Item label="退货单号">{order.purchase_return_no}</Descriptions.Item>
              <Descriptions.Item label="原采购单">{order.purchase_order_no}</Descriptions.Item>
              <Descriptions.Item label="供应商">{order.supplier_name}</Descriptions.Item>
              <Descriptions.Item label="仓库">{order.warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag>{purchaseReturnStatusLabel(order.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="结算类型">
                {purchaseReturnSettlementLabel(order.settlement_type)}
              </Descriptions.Item>
              <Descriptions.Item label="退款状态">
                {purchaseReturnRefundStatusLabel(order.refund_status)}
              </Descriptions.Item>
              <Descriptions.Item label="申请退款">
                {formatPurchaseAmount(order.requested_refund_amount)}
              </Descriptions.Item>
              <Descriptions.Item label="批准退款">
                {formatPurchaseAmount(order.approved_refund_amount)}
              </Descriptions.Item>
              <Descriptions.Item label="原因" span={3}>
                {order.reason}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <Card title="退货明细" className="mb-4">
            <AppTable
              rowKey="id"
              fillHeight={false}
              pagination={false}
              columns={columns}
              dataSource={order.items}
              scroll={{ x: 1400 }}
            />
          </Card>
          <Card title="退货出库记录" className="mb-4">
            <AppTable
              rowKey="id"
              fillHeight={false}
              pagination={false}
              dataSource={order.outbounds}
              locale={{ emptyText: '还没有退货出库记录' }}
              columns={[
                { title: '出库单号', dataIndex: 'outbound_no', width: 160 },
                { title: '状态', dataIndex: 'status', width: 100 },
                {
                  title: '确认时间',
                  dataIndex: 'confirmed_at',
                  width: 170,
                  render: (value: string | null) => (value ? formatDateTime(value) : '-'),
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 160,
                  render: (_, row) =>
                    row.status === 'DRAFT' ? (
                      <Can permission={PERMISSION_CODE.purchaseReturnOutbound}>
                        <Space>
                          <Button
                            type="link"
                            onClick={() => {
                              modal.confirm({
                                title: '确认退货出库',
                                content:
                                  '确认后将正式减少当前仓库库存，并生成采购退货库存流水，操作不可直接撤销。',
                                onOk: async () => {
                                  await confirmPurchaseReturnOutbound(row.id);
                                  message.success('已确认出库');
                                  invalidate();
                                },
                              });
                            }}
                          >
                            确认出库
                          </Button>
                          <Button type="link" onClick={() => navigate(`/purchase-return-outbounds/${row.id}`)}>
                            详情
                          </Button>
                        </Space>
                      </Can>
                    ) : (
                      <Button type="link" onClick={() => navigate(`/purchase-return-outbounds/${row.id}`)}>
                        详情
                      </Button>
                    ),
                },
              ]}
            />
          </Card>
          <Card title="供应商退款记录">
            <AppTable
              rowKey="id"
              fillHeight={false}
              pagination={false}
              dataSource={order.refunds}
              locale={{ emptyText: order.settlement_type === 'NO_REFUND' ? '本单不跟踪供应商退款' : '还没有退款记录' }}
              columns={[
                { title: '退款编号', dataIndex: 'refund_no', width: 160 },
                {
                  title: '金额',
                  dataIndex: 'amount',
                  width: 110,
                  render: (value: number) => formatPurchaseAmount(value),
                },
                { title: '状态', dataIndex: 'status', width: 100 },
                {
                  title: '外部流水号',
                  dataIndex: 'external_reference_no',
                  width: 160,
                  render: (value: string | null) => value || '-',
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 140,
                  render: (_, row) =>
                    row.status === 'PENDING' ? (
                      <Can permission={PERMISSION_CODE.supplierRefundConfirm}>
                        <Space>
                          <Button
                            type="link"
                            onClick={async () => {
                              await confirmSupplierRefund(row.id, {});
                              message.success('已确认退款成功');
                              invalidate();
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
                                    onChange={(event) => {
                                      reason = event.target.value;
                                    }}
                                  />
                                ),
                                onOk: async () => {
                                  if (!reason.trim()) {
                                    message.error('请填写失败原因');
                                    return Promise.reject();
                                  }
                                  await failSupplierRefund(row.id, { failure_reason: reason.trim() });
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
        onOk={async () => {
          await approvePurchaseReturn(returnId, {
            items: (order?.items ?? []).map((item) => ({
              item_id: item.id,
              approved_return_quantity: approveDraft[item.id]?.approved_return_quantity ?? item.requested_return_quantity,
              approved_refund_amount:
                approveDraft[item.id]?.approved_refund_amount ?? item.requested_refund_amount ?? 0,
            })),
          });
          message.success('已审核通过');
          setApproveOpen(false);
          invalidate();
        }}
        width={760}
      >
        <AppTable
          rowKey="id"
          size="small"
          pagination={false}
          fillHeight={false}
          dataSource={order?.items ?? []}
          columns={[
            { title: 'SKU', dataIndex: 'sku_code', width: 140 },
            { title: '申请退货', dataIndex: 'requested_return_quantity', width: 90 },
            {
              title: '批准退货',
              key: 'approved_return_quantity',
              width: 120,
              render: (_, record) => (
                <InputNumber
                  min={0}
                  max={record.requested_return_quantity}
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
              title: '批准退款',
              key: 'approved_refund_amount',
              width: 130,
              render: (_, record) => (
                <InputNumber
                  min={0}
                  max={record.requested_refund_amount ?? 0}
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
        title="创建退货出库单"
        open={outboundOpen}
        onCancel={() => setOutboundOpen(false)}
        onOk={async () => {
          const items = (order?.items ?? [])
            .map((item) => ({
              purchase_return_item_id: item.id,
              quantity: outboundQty[item.id] ?? 0,
            }))
            .filter((row) => row.quantity > 0);
          if (!items.length) {
            message.error('请填写本次实际退货数量');
            return Promise.reject();
          }
          const created = await createPurchaseReturnOutbound(returnId, { items });
          message.success('已创建出库草稿');
          setOutboundOpen(false);
          invalidate();
          navigate(`/purchase-return-outbounds/${created.id}`);
        }}
        width={820}
      >
        <p className="mb-3 text-sm text-slate-600">默认数量取剩余待退与当前可用库存的较小值。后端最终校验 available。</p>
        <AppTable
          rowKey="id"
          size="small"
          pagination={false}
          fillHeight={false}
          dataSource={order?.items ?? []}
          columns={[
            { title: 'SKU', dataIndex: 'sku_code', width: 130 },
            { title: '批准', dataIndex: 'approved_return_quantity', width: 80 },
            { title: '已退', dataIndex: 'returned_quantity', width: 80 },
            { title: '剩余待退', dataIndex: 'remaining_return_quantity', width: 90 },
            { title: '当前可用', dataIndex: 'inventory_available', width: 90 },
            {
              title: '本次退货',
              key: 'qty',
              width: 120,
              render: (_, record) => (
                <InputNumber
                  min={0}
                  max={record.remaining_return_quantity}
                  value={outboundQty[record.id]}
                  onChange={(value) => {
                    setOutboundQty((prev) => ({ ...prev, [record.id]: Number(value ?? 0) }));
                  }}
                />
              ),
            },
          ]}
        />
      </Modal>
      <Modal
        title="登记供应商退款"
        open={refundOpen}
        onCancel={() => setRefundOpen(false)}
        onOk={async () => {
          const created = await createPurchaseReturnRefund(returnId, {
            amount: refundAmount,
            external_reference_no: refundExternal.trim() || null,
          });
          await confirmSupplierRefund(created.id, { external_reference_no: refundExternal.trim() || null });
          message.success('已确认供应商退款成功');
          setRefundOpen(false);
          invalidate();
        }}
      >
        <p className="mb-2 text-sm text-slate-600">剩余可退 {formatPurchaseAmount(remainingRefund)}。本版只做 ERP 内人工确认。</p>
        <InputNumber
          className="mb-3 w-full"
          min={0}
          max={remainingRefund}
          precision={2}
          value={refundAmount}
          onChange={(value) => setRefundAmount(Number(value ?? 0))}
        />
        <Input
          placeholder="外部流水号（可选）"
          value={refundExternal}
          onChange={(event) => setRefundExternal(event.target.value)}
        />
      </Modal>
    </FormPageContainer>
  );
}
