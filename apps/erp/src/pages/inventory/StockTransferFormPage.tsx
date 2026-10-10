import {
  ApiError,
  canEditStockTransfer,
  PERMISSION_CODE,
  productSkuOptionsQueryKey,
  skuInventoryQueryKey,
  specValuesLabel,
  stockTransferQueryKey,
  stockTransfersQueryKey,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type SkuOption,
  type TransferSkuDraft,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Form, Input, InputNumber, Select, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchSkuAvailability, fetchSkuOptions } from '@/api/inventory';
import { createStockTransfer, fetchStockTransfer, updateStockTransfer } from '@/api/stock-transfers';
import { fetchWarehouses } from '@/api/warehouses';
import { ActionCell, AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

interface HeaderForm {
  source_warehouse_id: number;
  target_warehouse_id: number;
  remark?: string;
}

export function StockTransferFormPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const params = useParams();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const [form] = Form.useForm<HeaderForm>();
  const transferId = Number(params.id);
  const isEdit = Number.isInteger(transferId) && transferId > 0;
  const [items, setItems] = useState<TransferSkuDraft[]>([]);
  const [skuSearch, setSkuSearch] = useState('');
  const [skuKeyword, setSkuKeyword] = useState('');
  const sourceWarehouseId = Form.useWatch('source_warehouse_id', form);

  useEffect(() => {
    const timer = window.setTimeout(() => setSkuKeyword(skuSearch.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [skuSearch]);

  const detailQuery = useQuery({
    queryKey: stockTransferQueryKey(tenantId, isEdit ? transferId : null),
    queryFn: ({ signal }) => fetchStockTransfer(transferId, signal),
    enabled: tenantId != null && isEdit,
  });

  useEffect(() => {
    const detail = detailQuery.data;
    if (!detail) {
      return;
    }
    if (!canEditStockTransfer(detail.status)) {
      message.warning('当前状态不能编辑，已跳转到详情');
      navigate(`/stock-transfers/${detail.id}`, { replace: true });
      return;
    }
    form.setFieldsValue({
      source_warehouse_id: detail.source_warehouse_id,
      target_warehouse_id: detail.target_warehouse_id,
      remark: detail.remark ?? '',
    });
    setItems(
      detail.items.map((item) => ({
        sku_id: item.sku_id,
        sku_code: item.sku_code,
        sku_name: item.sku_name,
        product_name: item.product_name,
        spec_values: item.spec_values,
        quantity: item.quantity,
      })),
    );
  }, [detailQuery.data, form, message, navigate]);

  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });
  const skuOptionsQuery = useQuery({
    queryKey: productSkuOptionsQueryKey(tenantId, { q: skuKeyword, page: 1, pageSize: 20 }),
    queryFn: ({ signal }) => fetchSkuOptions({ q: skuKeyword || undefined, page: 1, pageSize: 20 }, signal),
    enabled: tenantId != null,
  });
  const skuIds = items.map((item) => item.sku_id);
  const availabilityQuery = useQuery({
    queryKey: skuInventoryQueryKey(tenantId, sourceWarehouseId ?? null, skuIds),
    queryFn: ({ signal }) => {
      if (sourceWarehouseId == null) {
        throw new Error('请先选择调出仓');
      }
      return fetchSkuAvailability(sourceWarehouseId, skuIds, signal);
    },
    enabled:
      tenantId != null &&
      sourceWarehouseId != null &&
      skuIds.length > 0 &&
      hasPermission(PERMISSION_CODE.inventoryRead),
  });
  const stockBySku = useMemo(() => {
    const map = new Map<
      number,
      { quantity: number; reserved: number; available: number; initialized: boolean }
    >();
    for (const row of availabilityQuery.data?.items ?? []) {
      map.set(row.sku_id, {
        quantity: row.quantity,
        reserved: row.reserved_quantity,
        available: row.available_quantity,
        initialized: row.initialized,
      });
    }
    return map;
  }, [availabilityQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async (values: HeaderForm) => {
      const payload = {
        source_warehouse_id: values.source_warehouse_id,
        target_warehouse_id: values.target_warehouse_id,
        remark: values.remark?.trim() || null,
        items: items.map((item) => ({ sku_id: item.sku_id, quantity: item.quantity })),
      };
      if (isEdit) {
        return updateStockTransfer(transferId, payload);
      }
      return createStockTransfer(payload);
    },
    onSuccess: (data) => {
      message.success(isEdit ? '调拨草稿已保存' : '调拨草稿已创建，尚未扣减库存');
      void queryClient.invalidateQueries({ queryKey: stockTransfersQueryKey(tenantId) });
      void queryClient.invalidateQueries({ queryKey: stockTransferQueryKey(tenantId, data.id) });
      navigate(`/stock-transfers/${data.id}`);
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });

  const addSku = (option: SkuOption) => {
    if (items.some((item) => item.sku_id === option.id)) {
      message.info('同一 SKU 已在明细中，请直接修改数量');
      return;
    }
    setItems((current) => [
      ...current,
      {
        sku_id: option.id,
        sku_code: option.sku_code,
        sku_name: option.name,
        product_name: option.product_name,
        spec_values: option.spec_values,
        quantity: 1,
      },
    ]);
  };

  const columns: ColumnsType<TransferSkuDraft> = [
    { title: 'SKU', dataIndex: 'sku_code', width: 140, render: (value: string) => <CodeCell value={value} /> },
    {
      title: '商品',
      dataIndex: 'product_name',
      width: 160,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '规格',
      key: 'spec',
      width: 140,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    {
      title: '调出仓实际 / 预占 / 可用',
      key: 'stock',
      width: 220,
      render: (_, record) => {
        const stock = stockBySku.get(record.sku_id);
        if (!sourceWarehouseId) {
          return '请先选择调出仓';
        }
        if (!stock) {
          return availabilityQuery.isFetching ? '查询中' : '-';
        }
        if (!stock.initialized) {
          return '未建库存';
        }
        return `${stock.quantity} / ${stock.reserved} / ${stock.available}`;
      },
    },
    {
      title: '调拨数量',
      dataIndex: 'quantity',
      width: 130,
      render: (value: number, record) => (
        <InputNumber
          min={1}
          precision={0}
          value={value}
          onChange={(next) => {
            setItems((current) =>
              current.map((item) => (item.sku_id === record.sku_id ? { ...item, quantity: next ?? 1 } : item)),
            );
          }}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_, record) => (
        <ActionCell>
          <Button type="link" onClick={() => setItems((current) => current.filter((item) => item.sku_id !== record.sku_id))}>
            删除
          </Button>
        </ActionCell>
      ),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader title={props.title ?? (isEdit ? '编辑调拨' : '新建调拨')} description={props.description} />
      <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)}>
        <div className="grid max-w-4xl grid-cols-2 gap-4">
          <Form.Item name="source_warehouse_id" label="调出仓" rules={[{ required: true, message: '请选择调出仓' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={(warehouseQuery.data?.items ?? []).map((item) => ({
                value: item.id,
                label: `${item.name}（${item.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="target_warehouse_id"
            label="调入仓"
            rules={[{ required: true, message: '请选择调入仓' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={(warehouseQuery.data?.items ?? []).map((item) => ({
                value: item.id,
                label: `${item.name}（${item.code}）`,
              }))}
            />
          </Form.Item>
        </div>
        <Form.Item name="remark" label="备注" className="max-w-4xl">
          <Input.TextArea rows={2} maxLength={255} />
        </Form.Item>
        <div className="mb-3 max-w-md">
          <Select
            showSearch
            filterOption={false}
            placeholder="远程搜索并添加 SKU"
            onSearch={setSkuSearch}
            onSelect={(_, option) => {
              const found = (skuOptionsQuery.data?.items ?? []).find((item) => item.id === option.value);
              if (found) {
                addSku(found);
              }
            }}
            options={(skuOptionsQuery.data?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.sku_code} ${item.product_name} ${item.name}`,
            }))}
          />
        </div>
        <AppTable rowKey="sku_id" columns={columns} dataSource={items} pagination={false} />
        <Space className="mt-4">
          <Button onClick={() => navigate('/stock-transfers')}>返回</Button>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending} disabled={items.length === 0}>
            保存草稿
          </Button>
        </Space>
      </Form>
    </FormPageContainer>
  );
}
