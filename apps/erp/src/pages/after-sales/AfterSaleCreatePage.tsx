import {
  AFTER_SALE_TYPE,
  AFTER_SALE_TYPE_OPTIONS,
  afterSalePreviewQueryKey,
  ApiError,
  formatSalesAmount,
  salesOrderStatusLabel,
  specValuesLabel,
  type AfterSalePreviewItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Descriptions, Input, InputNumber, Radio, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createAfterSale, fetchAfterSalePreview } from '@/api/after-sales';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

interface DraftLine {
  return_quantity: number;
  requested_refund_amount: number;
  reason: string;
}

export function AfterSaleCreatePage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [search] = useSearchParams();
  const salesOrderId = Number(search.get('salesOrderId'));
  const validId = Number.isInteger(salesOrderId) && salesOrderId > 0;
  const [saleType, setSaleType] = useState<string>(AFTER_SALE_TYPE.returnAndRefund);
  const [reason, setReason] = useState('');
  const [description, setDescription] = useState('');
  const [draft, setDraft] = useState<Record<number, DraftLine>>({});

  const previewQuery = useQuery({
    queryKey: afterSalePreviewQueryKey(tenantId, validId ? salesOrderId : null),
    queryFn: ({ signal }) => fetchAfterSalePreview(salesOrderId, signal),
    enabled: tenantId != null && validId,
  });
  const preview = previewQuery.data;

  useEffect(() => {
    if (!preview) {
      return;
    }
    const next: Record<number, DraftLine> = {};
    for (const item of preview.items) {
      next[item.sales_order_item_id] = {
        return_quantity: saleType === AFTER_SALE_TYPE.refundOnly ? 0 : item.returnable_quantity,
        requested_refund_amount:
          saleType === AFTER_SALE_TYPE.returnOnly
            ? 0
            : Number(item.refundable_amount.toFixed(2)),
        reason: '',
      };
    }
    setDraft(next);
  }, [preview, saleType]);

  const totalReturn = useMemo(
    () => Object.values(draft).reduce((sum, row) => sum + (row.return_quantity || 0), 0),
    [draft],
  );
  const totalRefund = useMemo(
    () => Object.values(draft).reduce((sum, row) => sum + (row.requested_refund_amount || 0), 0),
    [draft],
  );

  const mutation = useMutation({
    mutationFn: createAfterSale,
    onSuccess: (created) => {
      message.success('售后申请已提交');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sales'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sale-preview'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-order'] });
      navigate(`/after-sales/${created.id}`);
    },
    onError: (error: unknown) => message.error(error instanceof ApiError ? error.message : '创建失败'),
  });

  const columns: ColumnsType<AfterSalePreviewItem> = [
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
    { title: '已占用', dataIndex: 'occupied_return_quantity', width: 80 },
    { title: '可退数量', dataIndex: 'returnable_quantity', width: 90 },
    {
      title: '本次退货',
      key: 'return_quantity',
      width: 120,
      render: (_, record) => (
        <InputNumber
          min={0}
          max={record.returnable_quantity}
          disabled={saleType === AFTER_SALE_TYPE.refundOnly}
          value={draft[record.sales_order_item_id]?.return_quantity ?? 0}
          onChange={(value) => {
            setDraft((prev) => ({
              ...prev,
              [record.sales_order_item_id]: {
                ...prev[record.sales_order_item_id],
                return_quantity: Number(value ?? 0),
              },
            }));
          }}
        />
      ),
    },
    {
      title: '申请退款',
      key: 'requested_refund_amount',
      width: 130,
      render: (_, record) => (
        <InputNumber
          min={0}
          max={record.refundable_amount}
          precision={2}
          disabled={saleType === AFTER_SALE_TYPE.returnOnly}
          value={draft[record.sales_order_item_id]?.requested_refund_amount ?? 0}
          onChange={(value) => {
            setDraft((prev) => ({
              ...prev,
              [record.sales_order_item_id]: {
                ...prev[record.sales_order_item_id],
                requested_refund_amount: Number(value ?? 0),
              },
            }));
          }}
        />
      ),
    },
  ];

  const submit = () => {
    if (!preview) {
      return;
    }
    if (!reason.trim()) {
      message.error('请填写申请原因');
      return;
    }
    const items = preview.items
      .map((item) => {
        const line = draft[item.sales_order_item_id];
        return {
          sales_order_item_id: item.sales_order_item_id,
          return_quantity: saleType === AFTER_SALE_TYPE.refundOnly ? 0 : line?.return_quantity ?? 0,
          requested_refund_amount:
            saleType === AFTER_SALE_TYPE.returnOnly ? 0 : line?.requested_refund_amount ?? 0,
          reason: line?.reason || null,
        };
      })
      .filter((item) => item.return_quantity > 0 || item.requested_refund_amount > 0);
    if (!items.length) {
      message.error('请至少填写一行退货数量或退款金额');
      return;
    }
    mutation.mutate({
      sales_order_id: preview.sales_order_id,
      type: saleType,
      reason: reason.trim(),
      description: description.trim() || null,
      items,
    });
  };

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '申请售后'}
        description={props.description ?? '创建售后不改库存，也不改原销售明细数量。'}
        extra={
          <Space>
            <Button onClick={() => navigate(-1)}>返回</Button>
            <Button type="primary" loading={mutation.isPending} onClick={submit} disabled={!preview?.eligible}>
              提交申请
            </Button>
          </Space>
        }
      />
      {!validId ? <Alert type="warning" showIcon message="请从已履约的销售订单详情进入申请售后。" /> : null}
      {preview && !preview.eligible ? (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message="尚未正式出库的订单不能申请售后，请取消订单释放预占。"
        />
      ) : null}
      {preview ? (
        <>
          <Card className="mb-4">
            <Descriptions column={2} size="small">
              <Descriptions.Item label="销售订单">{preview.sales_order_no}</Descriptions.Item>
              <Descriptions.Item label="履约状态">{salesOrderStatusLabel(preview.status)}</Descriptions.Item>
              <Descriptions.Item label="客户">{preview.customer_name}</Descriptions.Item>
              <Descriptions.Item label="仓库">{preview.warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="币种">{preview.currency_code}</Descriptions.Item>
              <Descriptions.Item label="订单金额">{formatSalesAmount(preview.total_amount)}</Descriptions.Item>
            </Descriptions>
            <div className="mt-3">
              <Radio.Group
                value={saleType}
                onChange={(event) => setSaleType(event.target.value)}
                options={AFTER_SALE_TYPE_OPTIONS.map((item) => ({
                  value: item.value,
                  label: `${item.label}：${item.description}`,
                }))}
              />
            </div>
            <div className="mt-3 flex flex-col gap-2">
              <Input
                maxLength={255}
                placeholder="申请原因"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <Input.TextArea
                rows={2}
                maxLength={512}
                placeholder="补充说明（可选）"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <p className="mt-3 mb-0 text-sm text-slate-600">
              本次退货 {totalReturn}，申请退款 {formatSalesAmount(totalRefund)}
            </p>
          </Card>
          <Card title="售后明细" className='mt-4!'>
            <AppTable
              rowKey="sales_order_item_id"
              size="small"
              columns={columns}
              dataSource={preview.items}
              pagination={false}
              fillHeight={false}
            />
          </Card>
        </>
      ) : null}
    </FormPageContainer>
  );
}
