import {
  ApiError,
  canEditPurchaseOrder,
  mergePurchaseSkuLine,
  PERMISSION_CODE,
  productSkuOptionsQueryKey,
  purchaseLineAmount,
  purchaseOrderQueryKey,
  specValuesLabel,
  SUPPLIER_STATUS,
  suppliersQueryKey,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type PurchaseSkuDraft,
  type SkuOption,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Form, Input, InputNumber, Select, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchSkuOptions } from '@/api/inventory';
import { createPurchaseOrder, fetchPurchaseOrder, updatePurchaseOrder } from '@/api/purchase-orders';
import { fetchSuppliers } from '@/api/suppliers';
import { fetchWarehouses } from '@/api/warehouses';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

interface HeaderForm {
  supplier_id: number;
  warehouse_id: number;
  expected_arrival_date?: string | null;
  remark?: string;
}

function toPayloadItems(items: PurchaseSkuDraft[]) {
  return items.map((item) => ({
    sku_id: item.sku_id,
    quantity: item.quantity,
    unit_price: item.unit_price,
    remark: item.remark ?? null,
  }));
}

export function PurchaseFormPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const params = useParams();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const [form] = Form.useForm<HeaderForm>();
  const orderId = Number(params.id);
  const isEdit = Number.isInteger(orderId) && orderId > 0;
  const [items, setItems] = useState<PurchaseSkuDraft[]>([]);
  const [skuSearch, setSkuSearch] = useState('');
  const [skuKeyword, setSkuKeyword] = useState('');

  useEffect(() => {
    setItems([]);
    setSkuSearch('');
    setSkuKeyword('');
    form.resetFields();
  }, [tenantId, form]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSkuKeyword(skuSearch.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [skuSearch]);

  const detailQuery = useQuery({
    queryKey: purchaseOrderQueryKey(tenantId, isEdit ? orderId : null),
    queryFn: ({ signal }) => fetchPurchaseOrder(orderId, signal),
    enabled: tenantId != null && isEdit,
  });

  useEffect(() => {
    const detail = detailQuery.data;
    if (!detail) {
      return;
    }
    if (!canEditPurchaseOrder(detail.status)) {
      message.warning('当前状态不能编辑，已跳转到详情');
      navigate(`/purchases/${detail.id}`, { replace: true });
      return;
    }
    form.setFieldsValue({
      supplier_id: detail.supplier_id,
      warehouse_id: detail.warehouse_id,
      expected_arrival_date: detail.expected_arrival_date,
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
        unit_price: item.unit_price,
        remark: item.remark,
      })),
    );
  }, [detailQuery.data, form, message, navigate]);

  const supplierQuery = useQuery({
    queryKey: suppliersQueryKey(tenantId, { status: SUPPLIER_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchSuppliers({ status: SUPPLIER_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });

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

  const saveMutation = useMutation({
    mutationFn: async (values: HeaderForm) => {
      const payload = {
        supplier_id: values.supplier_id,
        warehouse_id: values.warehouse_id,
        expected_arrival_date: values.expected_arrival_date || null,
        remark: values.remark?.trim() || null,
        items: toPayloadItems(items),
      };
      if (isEdit) {
        return updatePurchaseOrder(orderId, payload);
      }
      return createPurchaseOrder(payload);
    },
    onSuccess: (data) => {
      message.success(isEdit ? '采购单已保存' : '采购单已创建');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-orders'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-order'] });
      navigate(`/purchases/${data.id}`);
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });

  const addSku = (option: SkuOption) => {
    const result = mergePurchaseSkuLine(items, {
      sku_id: option.id,
      sku_code: option.sku_code,
      sku_name: option.name,
      product_name: option.product_name,
      spec_values: option.spec_values,
      quantity: 1,
      unit_price: null,
    });
    setItems(result.items);
    if (result.merged) {
      message.info('同一 SKU 已合并数量');
    }
  };

  const columns: ColumnsType<PurchaseSkuDraft> = [
    { title: 'SKU', dataIndex: 'sku_code', key: 'sku_code', width: 140 },
    { title: '商品', dataIndex: 'product_name', key: 'product_name' },
    {
      title: '规格',
      key: 'spec',
      width: 160,
      render: (_, record) => specValuesLabel(record.spec_values),
    },
    {
      title: '数量',
      key: 'quantity',
      width: 120,
      render: (_, record) => (
        <InputNumber
          min={1}
          value={record.quantity}
          onChange={(value) => {
            const quantity = Number(value) || 1;
            setItems((prev) =>
              prev.map((item) => (item.sku_id === record.sku_id ? { ...item, quantity } : item)),
            );
          }}
        />
      ),
    },
    {
      title: '单价',
      key: 'unit_price',
      width: 130,
      render: (_, record) => (
        <InputNumber
          min={0}
          precision={2}
          value={record.unit_price ?? undefined}
          onChange={(value) => {
            setItems((prev) =>
              prev.map((item) =>
                item.sku_id === record.sku_id
                  ? { ...item, unit_price: value == null ? null : Number(value) }
                  : item,
              ),
            );
          }}
        />
      ),
    },
    {
      title: '金额',
      key: 'amount',
      width: 110,
      render: (_, record) => purchaseLineAmount(record.quantity, record.unit_price)?.toFixed(2) ?? '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          danger
          onClick={() => setItems((prev) => prev.filter((item) => item.sku_id !== record.sku_id))}
        >
          删除
        </Button>
      ),
    },
  ];

  const supplierOptions = useMemo(
    () => (supplierQuery.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name} (${item.code})` })),
    [supplierQuery.data],
  );
  const warehouseOptions = useMemo(
    () =>
      (warehouseQuery.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name} (${item.code})` })),
    [warehouseQuery.data],
  );
  const skuOptions = useMemo(
    () =>
      (skuOptionsQuery.data?.items ?? []).map((item) => ({
        value: item.id,
        label: `${item.sku_code} / ${item.product_name} / ${item.name}`,
        option: item,
      })),
    [skuOptionsQuery.data],
  );

  const canSave = isEdit
    ? hasPermission(PERMISSION_CODE.purchaseUpdate)
    : hasPermission(PERMISSION_CODE.purchaseCreate);

  return (
    <div>
      <PageHeader
        title={props.title ?? (isEdit ? '编辑采购单' : '新建采购单')}
        description={props.description ?? '同一采购单中同一个 SKU 只保留一行。审核通过后不会增加库存。'}
        extra={
          <Space>
            <Button onClick={() => navigate('/purchases')}>返回列表</Button>
          </Space>
        }
      />
      <Card className="mb-4">
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => {
            if (!items.length) {
              message.error('至少添加一条采购明细');
              return;
            }
            saveMutation.mutate(values);
          }}
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Form.Item
              name="supplier_id"
              label="供应商"
              rules={[{ required: true, message: '请选择供应商' }]}
            >
              <Select showSearch optionFilterProp="label" options={supplierOptions} />
            </Form.Item>
            <Form.Item name="warehouse_id" label="仓库" rules={[{ required: true, message: '请选择仓库' }]}>
              <Select showSearch optionFilterProp="label" options={warehouseOptions} />
            </Form.Item>
            <Form.Item name="expected_arrival_date" label="预计到货日期">
              <Input type="date" />
            </Form.Item>
            <Form.Item name="remark" label="备注">
              <Input.TextArea rows={1} maxLength={255} />
            </Form.Item>
          </div>
          <Form.Item label="添加 SKU">
            <Select
              showSearch
              filterOption={false}
              placeholder="搜索 SKU 编码或商品名称"
              onSearch={setSkuSearch}
              options={skuOptions}
              value={null}
              onChange={(_value, option) => {
                const selected = Array.isArray(option) ? option[0] : option;
                if (selected && 'option' in selected) {
                  addSku(selected.option as SkuOption);
                }
              }}
            />
          </Form.Item>
          <Table rowKey="sku_id" size="small" columns={columns} dataSource={items} pagination={false} />
          {canSave ? (
            <Button className="mt-4" type="primary" htmlType="submit" loading={saveMutation.isPending}>
              保存草稿
            </Button>
          ) : null}
        </Form>
      </Card>
    </div>
  );
}
