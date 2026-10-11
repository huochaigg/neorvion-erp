import {
  ApiError,
  formatPurchaseAmount,
  purchaseOrderStatusLabel,
  purchaseReturnPreviewQueryKey,
  PURCHASE_RETURN_SETTLEMENT,
  PURCHASE_RETURN_SETTLEMENT_OPTIONS,
  specValuesLabel,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type PurchaseReturnPreviewItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Card, Descriptions, Input, InputNumber, Radio, Select, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createPurchaseReturn, fetchPurchaseReturnPreview } from '@/api/purchase-returns';
import { fetchWarehouses } from '@/api/warehouses';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

interface DraftLine {
  requested_return_quantity: number;
  requested_refund_amount: number;
  reason: string;
}

export function PurchaseReturnCreatePage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [search] = useSearchParams();
  const purchaseOrderId = Number(search.get('purchaseOrderId'));
  const validId = Number.isInteger(purchaseOrderId) && purchaseOrderId > 0;
  const [settlement, setSettlement] = useState<string>(PURCHASE_RETURN_SETTLEMENT.refund);
  const [warehouseId, setWarehouseId] = useState<number>();
  const [reason, setReason] = useState('');
  const [description, setDescription] = useState('');
  const [draft, setDraft] = useState<Record<number, DraftLine>>({});

  const previewQuery = useQuery({
    queryKey: purchaseReturnPreviewQueryKey(tenantId, validId ? purchaseOrderId : null, warehouseId),
    queryFn: ({ signal }) => fetchPurchaseReturnPreview(purchaseOrderId, warehouseId, signal),
    enabled: tenantId != null && validId,
  });
  const preview = previewQuery.data;
  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });

  useEffect(() => {
    if (!preview) {
      return;
    }
    if (warehouseId == null) {
      setWarehouseId(preview.warehouse_id);
    }
    const next: Record<number, DraftLine> = {};
    for (const item of preview.items) {
      next[item.purchase_order_item_id] = {
        requested_return_quantity: item.returnable_quantity,
        requested_refund_amount:
          settlement === PURCHASE_RETURN_SETTLEMENT.noRefund
            ? 0
            : Number(item.refundable_amount.toFixed(2)),
        reason: '',
      };
    }
    setDraft(next);
  }, [preview, settlement, warehouseId]);

  const totalReturn = useMemo(
    () => Object.values(draft).reduce((sum, row) => sum + (row.requested_return_quantity || 0), 0),
    [draft],
  );
  const totalRefund = useMemo(
    () => Object.values(draft).reduce((sum, row) => sum + (row.requested_refund_amount || 0), 0),
    [draft],
  );

  const mutation = useMutation({
    mutationFn: createPurchaseReturn,
    onSuccess: (created) => {
      message.success('采购退货草稿已创建');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-returns'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-order'] });
      navigate(`/purchase-returns/${created.id}`);
    },
    onError: (error: unknown) => message.error(error instanceof ApiError ? error.message : '创建失败'),
  });

  const columns: ColumnsType<PurchaseReturnPreviewItem> = [
    { title: '商品', dataIndex: 'product_name', width: 150, render: (value: string) => <EllipsisCell value={value} /> },
    { title: 'SKU', dataIndex: 'sku_code', width: 130, render: (value: string) => <CodeCell value={value} /> },
    {
      title: '规格',
      key: 'spec',
      width: 120,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    { title: '采购数量', dataIndex: 'ordered_quantity', width: 90 },
    { title: '累计已收货', dataIndex: 'received_quantity', width: 100 },
    { title: '历史退货占用', dataIndex: 'occupied_return_quantity', width: 110 },
    { title: '当前可退', dataIndex: 'returnable_quantity', width: 90 },
    {
      title: '仓存可用',
      key: 'available',
      width: 160,
      render: (_, record) =>
        `实 ${record.inventory_quantity} / 预占 ${record.inventory_reserved} / 可用 ${record.inventory_available}`,
    },
    {
      title: '本次申请退货',
      key: 'requested_return_quantity',
      width: 130,
      render: (_, record) => (
        <InputNumber
          min={0}
          max={record.returnable_quantity}
          value={draft[record.purchase_order_item_id]?.requested_return_quantity}
          onChange={(value) => {
            setDraft((prev) => ({
              ...prev,
              [record.purchase_order_item_id]: {
                ...prev[record.purchase_order_item_id],
                requested_return_quantity: Number(value ?? 0),
              },
            }));
          }}
        />
      ),
    },
    {
      title: '采购单价',
      dataIndex: 'unit_price',
      width: 100,
      render: (value: number | null) => formatPurchaseAmount(value),
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
          disabled={settlement === PURCHASE_RETURN_SETTLEMENT.noRefund}
          value={draft[record.purchase_order_item_id]?.requested_refund_amount}
          onChange={(value) => {
            setDraft((prev) => ({
              ...prev,
              [record.purchase_order_item_id]: {
                ...prev[record.purchase_order_item_id],
                requested_refund_amount: Number(value ?? 0),
              },
            }));
          }}
        />
      ),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? '创建采购退货'}
        description={props.description}
        extra={
          <Space>
            <Button onClick={() => navigate(-1)}>返回</Button>
            <Button
              type="primary"
              loading={mutation.isPending}
              disabled={!preview?.eligible}
              onClick={() => {
                if (!reason.trim()) {
                  message.error('请填写退货原因');
                  return;
                }
                const items = (preview?.items ?? [])
                  .map((item) => ({
                    purchase_order_item_id: item.purchase_order_item_id,
                    requested_return_quantity: draft[item.purchase_order_item_id]?.requested_return_quantity ?? 0,
                    requested_refund_amount:
                      settlement === PURCHASE_RETURN_SETTLEMENT.noRefund
                        ? 0
                        : draft[item.purchase_order_item_id]?.requested_refund_amount ?? 0,
                    reason: draft[item.purchase_order_item_id]?.reason || null,
                  }))
                  .filter((row) => row.requested_return_quantity > 0);
                if (!items.length) {
                  message.error('至少选择一件要退的商品');
                  return;
                }
                mutation.mutate({
                  purchase_order_id: purchaseOrderId,
                  warehouse_id: warehouseId,
                  settlement_type: settlement,
                  reason: reason.trim(),
                  description: description.trim() || null,
                  items,
                });
              }}
            >
              创建草稿
            </Button>
          </Space>
        }
      />
      {!validId ? <Alert type="warning" showIcon message="请从已收货采购单详情进入创建采购退货。" /> : null}
      {preview && !preview.eligible ? (
        <Alert type="error" showIcon message="该采购单尚未实际收货，不能创建采购退货。" className="mb-4" />
      ) : null}
      {preview ? (
        <>
          <Card className="mb-4">
            <Descriptions column={3} size="small">
              <Descriptions.Item label="采购单号">{preview.purchase_order_no}</Descriptions.Item>
              <Descriptions.Item label="供应商">{preview.supplier_name}</Descriptions.Item>
              <Descriptions.Item label="采购状态">{purchaseOrderStatusLabel(preview.status)}</Descriptions.Item>
              <Descriptions.Item label="原采购仓库">{preview.original_warehouse_name}</Descriptions.Item>
              <Descriptions.Item label="退货仓库" span={2}>
                <Select
                  style={{ minWidth: 220 }}
                  value={warehouseId}
                  onChange={setWarehouseId}
                  options={(warehouseQuery.data?.items ?? []).map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                />
              </Descriptions.Item>
              <Descriptions.Item label="结算类型" span={3}>
                <Radio.Group
                  value={settlement}
                  onChange={(event) => setSettlement(event.target.value)}
                  options={PURCHASE_RETURN_SETTLEMENT_OPTIONS.map((item) => ({
                    value: item.value,
                    label: item.label,
                  }))}
                />
              </Descriptions.Item>
              <Descriptions.Item label="退货原因" span={3}>
                <Input value={reason} maxLength={255} onChange={(event) => setReason(event.target.value)} />
              </Descriptions.Item>
              <Descriptions.Item label="说明" span={3}>
                <Input.TextArea
                  rows={2}
                  value={description}
                  maxLength={512}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </Descriptions.Item>
              <Descriptions.Item label="本次申请">{totalReturn} 件</Descriptions.Item>
              <Descriptions.Item label="申请退款">{formatPurchaseAmount(totalRefund)}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Alert
            className="mb-4"
            type="info"
            showIcon
            message="可退数量按累计已收货计算，不是采购计划数量。申请可以超过当前仓库可用量，确认出库时单次最多只能用当时的 available。"
          />
          <AppTable
            rowKey="purchase_order_item_id"
            fillHeight={false}
            pagination={false}
            columns={columns}
            dataSource={preview.items}
            scroll={{ x: 1600 }}
          />
        </>
      ) : null}
    </FormPageContainer>
  );
}
