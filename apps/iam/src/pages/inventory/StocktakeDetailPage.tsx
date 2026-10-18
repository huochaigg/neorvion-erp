import {
  ApiError,
  canCancelStocktake,
  canConfirmStocktake,
  canEditStocktakeCount,
  canSubmitStocktake,
  inventoryQueryKey,
  inventoryTransactionsQueryKey,
  PERMISSION_CODE,
  specValuesLabel,
  stocktakeDifferenceText,
  stocktakeQueryKey,
  stocktakeScopeLabel,
  stocktakesQueryKey,
  stocktakeStatusLabel,
  type StocktakeItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Descriptions, Input, InputNumber, Popconfirm, Space, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  cancelStocktake,
  confirmStocktake,
  fetchStocktake,
  saveStocktakeItems,
  submitStocktake,
} from '@/api/stocktakes';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

interface DraftLine {
  counted_quantity: number | null;
  remark: string;
}

function differenceTag(difference: number | null) {
  const text = stocktakeDifferenceText(difference);
  if (difference == null) {
    return <Tag>{text}</Tag>;
  }
  if (difference > 0) {
    return <Tag color="success">{text}</Tag>;
  }
  if (difference < 0) {
    return <Tag color="error">{text}</Tag>;
  }
  return <Tag>{text}</Tag>;
}

export function StocktakeDetailPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const stocktakeId = Number(useParams().id);
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Record<number, DraftLine>>({});
  const query = useQuery({
    queryKey: stocktakeQueryKey(tenantId, stocktakeId),
    queryFn: ({ signal }) => fetchStocktake(stocktakeId, signal),
    enabled: tenantId != null && stocktakeId > 0,
  });
  const order = query.data;

  useEffect(() => {
    if (!order) {
      return;
    }
    const next: Record<number, DraftLine> = {};
    for (const item of order.items) {
      next[item.id] = {
        counted_quantity: item.counted_quantity,
        remark: item.remark ?? '',
      };
    }
    setDraft(next);
  }, [order]);

  async function refreshInventory() {
    await queryClient.invalidateQueries({ queryKey: stocktakeQueryKey(tenantId, stocktakeId) });
    await queryClient.invalidateQueries({ queryKey: stocktakesQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: inventoryQueryKey(tenantId) });
    await queryClient.invalidateQueries({ queryKey: inventoryTransactionsQueryKey(tenantId) });
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      saveStocktakeItems(
        stocktakeId,
        Object.entries(draft)
          .filter(([, row]) => row.counted_quantity != null)
          .map(([itemId, row]) => ({
            item_id: Number(itemId),
            counted_quantity: row.counted_quantity as number,
            remark: row.remark.trim() || null,
          })),
      ),
    onSuccess: async () => {
      message.success('实盘数量已保存，尚未调整库存');
      await queryClient.invalidateQueries({ queryKey: stocktakeQueryKey(tenantId, stocktakeId) });
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });
  const submitMutation = useMutation({
    mutationFn: () => submitStocktake(stocktakeId),
    onSuccess: async () => {
      message.success('已提交，等待确认');
      await refreshInventory();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '提交失败');
    },
  });
  const confirmMutation = useMutation({
    mutationFn: () => confirmStocktake(stocktakeId),
    onSuccess: async () => {
      message.success('已按盘点差异调整库存');
      await refreshInventory();
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '确认失败');
    },
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelStocktake(stocktakeId),
    onSuccess: async () => {
      message.success('盘点任务已取消');
      await refreshInventory();
    },
  });

  const allCounted = useMemo(() => {
    if (!order) {
      return false;
    }
    return order.items.every((item) => (draft[item.id]?.counted_quantity ?? item.counted_quantity) != null);
  }, [draft, order]);
  const editable = order ? canEditStocktakeCount(order.status) : false;

  const columns: ColumnsType<StocktakeItem> = [
    { title: 'SKU', dataIndex: 'sku_code', width: 140 },
    { title: '商品', dataIndex: 'product_name', width: 160 },
    {
      title: '规格',
      key: 'spec',
      width: 140,
      render: (_, row) => specValuesLabel(row.spec_values),
    },
    { title: '账面库存', dataIndex: 'system_quantity', width: 100 },
    { title: '账面预占', dataIndex: 'system_reserved_quantity', width: 100 },
    { title: '账面可用', dataIndex: 'system_available_quantity', width: 100 },
    {
      title: '实盘数量',
      dataIndex: 'counted_quantity',
      width: 130,
      render: (_, row) =>
        editable ? (
          <InputNumber
            min={0}
            precision={0}
            value={draft[row.id]?.counted_quantity ?? null}
            onChange={(value) =>
              setDraft((current) => ({
                ...current,
                [row.id]: {
                  counted_quantity: value == null ? null : Number(value),
                  remark: current[row.id]?.remark ?? '',
                },
              }))
            }
          />
        ) : (
          row.counted_quantity ?? '-'
        ),
    },
    {
      title: '差异',
      key: 'difference',
      width: 120,
      render: (_, row) => {
        const counted = editable ? (draft[row.id]?.counted_quantity ?? null) : row.counted_quantity;
        const diff = counted == null ? null : counted - row.system_quantity;
        return differenceTag(diff);
      },
    },
    {
      title: '备注',
      dataIndex: 'remark',
      width: 180,
      render: (_, row) =>
        editable ? (
          <Input
            value={draft[row.id]?.remark ?? ''}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                [row.id]: {
                  counted_quantity: current[row.id]?.counted_quantity ?? row.counted_quantity,
                  remark: event.target.value,
                },
              }))
            }
          />
        ) : (
          row.remark || '-'
        ),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? order?.stocktake_no ?? '盘点详情'}
        extra={
          <Space>
            <Button onClick={() => navigate('/stocktakes')}>返回列表</Button>
            {order && editable ? (
              <Can permission={PERMISSION_CODE.stocktakeUpdate}>
                <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                  保存实盘
                </Button>
              </Can>
            ) : null}
            {order && canSubmitStocktake(order.status, allCounted) ? (
              <Can permission={PERMISSION_CODE.stocktakeSubmit}>
                <Button type="primary" loading={submitMutation.isPending} onClick={() => submitMutation.mutate()}>
                  提交盘点
                </Button>
              </Can>
            ) : null}
            {order && canConfirmStocktake(order.status) ? (
              <Can permission={PERMISSION_CODE.stocktakeConfirm}>
                <Popconfirm
                  title="确认后将根据盘点差异调整真实库存并生成库存流水，操作不可直接撤销。"
                  onConfirm={() => confirmMutation.mutate()}
                >
                  <Button type="primary" loading={confirmMutation.isPending}>
                    确认盘点
                  </Button>
                </Popconfirm>
              </Can>
            ) : null}
            {order && canCancelStocktake(order.status) ? (
              <Can permission={PERMISSION_CODE.stocktakeCancel}>
                <Button danger loading={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
                  取消
                </Button>
              </Can>
            ) : null}
          </Space>
        }
      />
      {order ? (
        <>
          <Descriptions column={3} className="mb-4">
            <Descriptions.Item label="单号">{order.stocktake_no}</Descriptions.Item>
            <Descriptions.Item label="仓库">{order.warehouse_name}</Descriptions.Item>
            <Descriptions.Item label="范围">{stocktakeScopeLabel(order.scope)}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag>{stocktakeStatusLabel(order.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="创建人">{order.created_by_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatDateTime(order.created_at)}</Descriptions.Item>
            <Descriptions.Item label="SKU 数">{order.sku_count}</Descriptions.Item>
            <Descriptions.Item label="差异 SKU">{order.difference_sku_count}</Descriptions.Item>
            <Descriptions.Item label="备注">{order.remark || '-'}</Descriptions.Item>
          </Descriptions>
          <Typography.Paragraph type="secondary">
            账面库存是创建盘点时的快照。确认时按「实盘 − 快照」调整当前库存，不会覆盖盘点期间的入库出库。
          </Typography.Paragraph>
          <AppTable rowKey="id" columns={columns} dataSource={order.items} pagination={false} />
        </>
      ) : null}
    </FormPageContainer>
  );
}
