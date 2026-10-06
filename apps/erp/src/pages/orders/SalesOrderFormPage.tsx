import {
  ApiError,
  canEditSalesOrder,
  CUSTOMER_STATUS,
  customersQueryKey,
  mergeSalesSkuLine,
  PERMISSION_CODE,
  productSkuOptionsQueryKey,
  SALES_ORDER_SOURCE,
  SALES_ORDER_SOURCE_OPTIONS,
  salesLineAmount,
  salesOrderQueryKey,
  skuInventoryQueryKey,
  specValuesLabel,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type Customer,
  type SalesSkuDraft,
  type SkuOption,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Form, Input, InputNumber, Select, Space } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchCustomers } from '@/api/customers';
import { fetchSkuAvailability, fetchSkuOptions } from '@/api/inventory';
import { createSalesOrder, fetchSalesOrder, updateSalesOrder } from '@/api/sales-orders';
import { fetchWarehouses } from '@/api/warehouses';
import { ActionCell, AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import type { PageProps } from '@/router/types';

interface HeaderForm {
  customer_id: number;
  warehouse_id: number;
  source?: string;
  external_order_no?: string;
  recipient_name?: string;
  recipient_phone?: string;
  country_code?: string;
  province?: string;
  city?: string;
  address?: string;
  remark?: string;
}

function emptyToNull(value?: string) {
  const text = value?.trim();
  return text ? text : null;
}

export function SalesOrderFormPage(props: PageProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const params = useParams();
  const queryClient = useQueryClient();
  const { tenantId, hasPermission } = usePermissions();
  const [form] = Form.useForm<HeaderForm>();
  const orderId = Number(params.id);
  const isEdit = Number.isInteger(orderId) && orderId > 0;
  const [items, setItems] = useState<SalesSkuDraft[]>([]);
  const [skuSearch, setSkuSearch] = useState('');
  const [skuKeyword, setSkuKeyword] = useState('');
  const warehouseId = Form.useWatch('warehouse_id', form);

  useEffect(() => {
    setItems([]);
    setSkuSearch('');
    setSkuKeyword('');
    form.resetFields();
    form.setFieldValue('source', SALES_ORDER_SOURCE.manual);
  }, [tenantId, form]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSkuKeyword(skuSearch.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [skuSearch]);

  const detailQuery = useQuery({
    queryKey: salesOrderQueryKey(tenantId, isEdit ? orderId : null),
    queryFn: ({ signal }) => fetchSalesOrder(orderId, signal),
    enabled: tenantId != null && isEdit,
  });

  useEffect(() => {
    const detail = detailQuery.data;
    if (!detail) {
      return;
    }
    if (!canEditSalesOrder(detail.status)) {
      message.warning('当前状态不能编辑，已跳转到详情');
      navigate(`/orders/${detail.id}`, { replace: true });
      return;
    }
    form.setFieldsValue({
      customer_id: detail.customer_id,
      warehouse_id: detail.warehouse_id,
      source: detail.source,
      external_order_no: detail.external_order_no ?? '',
      recipient_name: detail.recipient_name ?? '',
      recipient_phone: detail.recipient_phone ?? '',
      country_code: detail.country_code ?? '',
      province: detail.province ?? '',
      city: detail.city ?? '',
      address: detail.address ?? '',
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

  const customerQuery = useQuery({
    queryKey: customersQueryKey(tenantId, { status: CUSTOMER_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) => fetchCustomers({ status: CUSTOMER_STATUS.active, page: 1, pageSize: 100 }, signal),
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
  const skuIds = items.map((item) => item.sku_id);
  const availabilityQuery = useQuery({
    queryKey: skuInventoryQueryKey(tenantId, warehouseId ?? null, skuIds),
    queryFn: ({ signal }) => fetchSkuAvailability(warehouseId, skuIds, signal),
    enabled: tenantId != null && warehouseId != null && skuIds.length > 0 && hasPermission(PERMISSION_CODE.inventoryRead),
  });

  const availableBySku = useMemo(() => {
    const map = new Map<number, { available: number; initialized: boolean }>();
    for (const row of availabilityQuery.data?.items ?? []) {
      map.set(row.sku_id, { available: row.available_quantity, initialized: row.initialized });
    }
    return map;
  }, [availabilityQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async (values: HeaderForm) => {
      const payload = {
        customer_id: values.customer_id,
        warehouse_id: values.warehouse_id,
        source: values.source || SALES_ORDER_SOURCE.manual,
        external_order_no: emptyToNull(values.external_order_no),
        currency_code: 'CNY', // 默认 CNY TODO 后期支持多币种
        recipient_name: emptyToNull(values.recipient_name),
        recipient_phone: emptyToNull(values.recipient_phone),
        country_code: emptyToNull(values.country_code)?.toUpperCase() ?? null,
        province: emptyToNull(values.province),
        city: emptyToNull(values.city),
        address: emptyToNull(values.address),
        remark: emptyToNull(values.remark),
        items: items.map((item) => ({
          sku_id: item.sku_id,
          quantity: item.quantity,
          unit_price: item.unit_price,
          remark: item.remark ?? null,
        })),
      };
      if (isEdit) {
        return updateSalesOrder(orderId, payload);
      }
      return createSalesOrder(payload);
    },
    onSuccess: (data) => {
      message.success(isEdit ? '销售订单已保存' : '销售订单已创建');
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-orders'] });
      void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-order'] });
      navigate(`/orders/${data.id}`);
    },
    onError: (error: unknown) => {
      message.error(error instanceof ApiError ? error.message : '保存失败');
    },
  });

  const fillFromCustomer = (customerId: number) => {
    const customer = (customerQuery.data?.items ?? []).find((item) => item.id === customerId);
    if (!customer) {
      return;
    }
    form.setFieldsValue({
      recipient_name: customer.name,
      recipient_phone: customer.phone ?? '',
      country_code: customer.country_code ?? '',
      province: customer.province ?? '',
      city: customer.city ?? '',
      address: customer.address ?? '',
    });
  };

  const addSku = (option: SkuOption) => {
    const result = mergeSalesSkuLine(items, {
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
      message.info('同一 SKU 已在明细中，请直接修改数量');
    }
  };

  const columns: ColumnsType<SalesSkuDraft> = [
    { title: 'SKU', dataIndex: 'sku_code', key: 'sku_code', width: 150, render: (value: string) => <CodeCell value={value} /> },
    { title: '商品', dataIndex: 'product_name', key: 'product_name', width: 160, render: (value: string) => <EllipsisCell value={value} /> },
    {
      title: '规格',
      key: 'spec',
      width: 140,
      render: (_, record) => <EllipsisCell value={specValuesLabel(record.spec_values)} />,
    },
    {
      title: '当前可用库存',
      key: 'available',
      width: 220,
      render: (_, record) => {
        const stock = availableBySku.get(record.sku_id);
        if (!warehouseId) {
          return '请先选择仓库';
        }
        if (!stock) {
          return availabilityQuery.isFetching ? '查询中' : '-';
        }
        const short = record.quantity > stock.available;
        return (
          <div>
            <div>{stock.initialized ? stock.available : '未建库存'}</div>
            {short ? <div className="text-xs text-amber-600">当前库存可能不足，订单确认时将再次校验。</div> : null}
          </div>
        );
      },
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 120,
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
      title: '单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 140,
      render: (value: number | null, record) => (
        <InputNumber
          min={0}
          precision={2}
          value={value ?? undefined}
          onChange={(next) => {
            setItems((current) =>
              current.map((item) =>
                item.sku_id === record.sku_id ? { ...item, unit_price: next ?? null } : item,
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
      render: (_, record) => {
        const amount = salesLineAmount(record.quantity, record.unit_price);
        return amount == null ? '-' : amount.toFixed(2);
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" danger onClick={() => setItems((current) => current.filter((item) => item.sku_id !== record.sku_id))}>
            移除
          </Button>
        </ActionCell>
      ),
    },
  ];

  return (
    <FormPageContainer>
      <PageHeader
        title={props.title ?? (isEdit ? '编辑销售订单' : '新建销售订单')}
        description={props.description ?? '草稿只保存收货快照，不预占库存。库存不足也可以先保存。'}
        extra={
          <Space>
            <Button onClick={() => navigate(isEdit ? `/orders/${orderId}` : '/orders/list')}>返回</Button>
            <Button type="primary" loading={saveMutation.isPending} onClick={() => form.submit()}>
              保存草稿
            </Button>
          </Space>
        }
      />
      <Form
        form={form}
        layout="vertical"
        initialValues={{ source: SALES_ORDER_SOURCE.manual }}
        onFinish={(values) => {
          if (items.length === 0) {
            message.error('请至少添加一个 SKU');
            return;
          }
          saveMutation.mutate(values);
        }}
      >
        <Card title="基础信息" className="mb-4">
          <div className="grid gap-x-4 md:grid-cols-2">
            <Form.Item name="customer_id" label="客户" rules={[{ required: true, message: '请选择客户' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                placeholder="选择客户"
                options={(customerQuery.data?.items ?? []).map((item: Customer) => ({
                  value: item.id,
                  label: `${item.name} (${item.code})`,
                }))}
                onChange={fillFromCustomer}
              />
            </Form.Item>
            <Form.Item name="warehouse_id" label="履约仓库" rules={[{ required: true, message: '请选择仓库' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                placeholder="选择仓库"
                options={(warehouseQuery.data?.items ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} (${item.code})`,
                }))}
              />
            </Form.Item>
            <Form.Item name="source" label="来源">
              <Select options={SALES_ORDER_SOURCE_OPTIONS} />
            </Form.Item>
            <Form.Item name="external_order_no" label="平台订单号">
              <Input maxLength={64} placeholder="手工单可以留空" />
            </Form.Item>
            <Form.Item name="recipient_name" label="收件人" rules={[{ required: true, message: '请填写收件人' }]}>
              <Input maxLength={128} />
            </Form.Item>
            <Form.Item name="recipient_phone" label="联系电话">
              <Input maxLength={32} />
            </Form.Item>
            <Form.Item name="country_code" label="国家">
              <Input maxLength={2} placeholder="CN" />
            </Form.Item>
            <Form.Item name="province" label="省 / 州">
              <Input maxLength={64} />
            </Form.Item>
            <Form.Item name="city" label="城市">
              <Input maxLength={64} />
            </Form.Item>
            <Form.Item name="address" label="详细地址" rules={[{ required: true, message: '请填写详细地址' }]}>
              <Input maxLength={255} />
            </Form.Item>
          </div>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} maxLength={255} />
          </Form.Item>
        </Card>
      </Form>
      <Card
        title="订单明细"
        extra={
          <Select
            showSearch
            filterOption={false}
            placeholder="搜索 SKU 编码或商品名称"
            style={{ width: 280 }}
            value={null}
            searchValue={skuSearch}
            onSearch={setSkuSearch}
            options={(skuOptionsQuery.data?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.sku_code} ${item.product_name}`,
            }))}
            onChange={(value) => {
              const found = (skuOptionsQuery.data?.items ?? []).find((item) => item.id === value);
              if (found) {
                addSku(found);
              }
              setSkuSearch('');
            }}
          />
        }
      >
        <AppTable rowKey="sku_id" size="small" columns={columns} dataSource={items} pagination={false} fillHeight={false} />
      </Card>
    </FormPageContainer>
  );
}
