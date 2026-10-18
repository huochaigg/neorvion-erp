import {
  ApiError,
  canCancelSalesOrder,
  canConfirmSalesOrder,
  canEditSalesOrder,
  canSubmitSalesOrder,
  CUSTOMER_STATUS,
  customersQueryKey,
  DEFAULT_PAGE_SIZE,
  formatSalesAmount,
  formatSalesInventoryShortage,
  PERMISSION_CODE,
  SALES_ORDER_SOURCE_OPTIONS,
  SALES_ORDER_STATUS_OPTIONS,
  salesOrderSourceLabel,
  salesOrdersQueryKey,
  salesOrderStatusLabel,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type SalesOrderListItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchCustomers } from '@/api/customers';
import { cancelSalesOrder, confirmSalesOrder, fetchSalesOrders, submitSalesOrder } from '@/api/sales-orders';
import { fetchWarehouses } from '@/api/warehouses';
import { AppRangePicker } from '@/components/AppDatePicker';
import { ActionCell, AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

function statusTag(status: string) {
  const color =
    status === 'PENDING_CONFIRMATION' ? 'processing' : status === 'WAITING_OUTBOUND' ? 'blue' : 'default';
  return <Tag color={color}>{salesOrderStatusLabel(status)}</Tag>;
}

function errorText(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) {
    return fallback;
  }
  return formatSalesInventoryShortage(error.data, error.message || fallback);
}

function invalidateOrders(queryClient: ReturnType<typeof useQueryClient>, tenantId: number | null) {
  void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-orders'] });
  void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sales-order'] });
  void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory'] });
  void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'inventory-transactions'] });
  void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'sku-inventory'] });
}

export function SalesOrderListPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [customerId, setCustomerId] = useState<number | undefined>();
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [source, setSource] = useState<string | undefined>();
  const [skuCode, setSkuCode] = useState('');
  const [productName, setProductName] = useState('');
  const [createdRange, setCreatedRange] = useState<[string, string] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setQ('');
    setKeyword('');
    setCustomerId(undefined);
    setWarehouseId(undefined);
    setStatus(undefined);
    setSource(undefined);
    setSkuCode('');
    setProductName('');
    setCreatedRange(null);
    setPage(1);
  }, [tenantId]);

  const filters = {
    q: keyword,
    customerId,
    warehouseId,
    status,
    source,
    skuCode: skuCode.trim() || undefined,
    productName: productName.trim() || undefined,
    createdFrom: createdRange?.[0],
    createdTo: createdRange?.[1],
    page,
    pageSize,
  };

  const listQuery = useQuery({
    queryKey: salesOrdersQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchSalesOrders(filters, signal),
    enabled: tenantId != null,
  });

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

  const submitMutation = useMutation({
    mutationFn: submitSalesOrder,
    onSuccess: () => {
      message.success('已提交，等待确认');
      invalidateOrders(queryClient, tenantId);
    },
    onError: (error: unknown) => message.error(errorText(error, '提交失败')),
  });
  const confirmMutation = useMutation({
    mutationFn: confirmSalesOrder,
    onSuccess: () => {
      message.success('已确认并预占库存');
      invalidateOrders(queryClient, tenantId);
    },
    onError: (error: unknown) => message.error(errorText(error, '确认失败')),
  });

  const columns: ColumnsType<SalesOrderListItem> = [
    {
      title: '订单号',
      dataIndex: 'order_no',
      key: 'order_no',
      width: 160,
      render: (value: string) => <CodeCell value={value} />,
    },
    {
      title: '客户',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 160,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 110,
      render: (value: string) => salesOrderSourceLabel(value),
    },
    {
      title: '仓库',
      dataIndex: 'warehouse_name',
      key: 'warehouse_name',
      width: 160,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    { title: 'SKU 种类', dataIndex: 'sku_count', key: 'sku_count', width: 110 },
    { title: '商品总数量', dataIndex: 'total_quantity', key: 'total_quantity', width: 120 },
    {
      title: '订单金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 120,
      render: (value: number | null) => formatSalesAmount(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (value: string) => statusTag(value),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right',
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => navigate(`/orders/${record.id}`)}>
            详情
          </Button>
          {canEditSalesOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.orderUpdate}>
              <Button type="link" size="small" onClick={() => navigate(`/orders/${record.id}/edit`)}>
                编辑
              </Button>
            </Can>
          ) : null}
          {canSubmitSalesOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.orderSubmit}>
              <Button type="link" size="small" onClick={() => submitMutation.mutate(record.id)}>
                提交
              </Button>
            </Can>
          ) : null}
          {canConfirmSalesOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.orderAudit}>
              <Button type="link" size="small" onClick={() => confirmMutation.mutate(record.id)}>
                确认
              </Button>
            </Can>
          ) : null}
          {canCancelSalesOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.orderCancel}>
              <Button
                type="link"
                size="small"
                danger
                onClick={() => {
                  let reason = '';
                  modal.confirm({
                    title: '取消销售订单',
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
                        await cancelSalesOrder(record.id, reason.trim() || null);
                        message.success(record.status === 'WAITING_OUTBOUND' ? '已取消并释放库存' : '已取消');
                        invalidateOrders(queryClient, tenantId);
                      } catch (error) {
                        message.error(errorText(error, '取消失败'));
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
        </ActionCell>
      ),
    },
  ];

  const customerOptions = useMemo(
    () => (customerQuery.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name} (${item.code})` })),
    [customerQuery.data],
  );
  const warehouseOptions = useMemo(
    () =>
      (warehouseQuery.data?.items ?? []).map((item) => ({ value: item.id, label: `${item.name} (${item.code})` })),
    [warehouseQuery.data],
  );

  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '销售订单'}
        description={props.description ?? '确认后预占库存，不减少实际库存。取消待出库订单会释放预占。'}
        extra={
          <Can permission={PERMISSION_CODE.orderCreate}>
            <Button type="primary" onClick={() => navigate('/orders/create')}>
              新建销售订单
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="订单号 / 平台单号 / 客户"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onSearch={(value) => {
              setKeyword(value.trim());
              setPage(1);
            }}
            style={{ width: 240 }}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="客户"
            value={customerId}
            style={{ width: 180 }}
            options={customerOptions}
            onChange={(value) => {
              setCustomerId(value);
              setPage(1);
            }}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="仓库"
            value={warehouseId}
            style={{ width: 180 }}
            options={warehouseOptions}
            onChange={(value) => {
              setWarehouseId(value);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            value={status}
            style={{ width: 130 }}
            options={SALES_ORDER_STATUS_OPTIONS}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="来源"
            value={source}
            style={{ width: 130 }}
            options={SALES_ORDER_SOURCE_OPTIONS}
            onChange={(value) => {
              setSource(value);
              setPage(1);
            }}
          />
          <Input
            allowClear
            placeholder="SKU 编码"
            value={skuCode}
            style={{ width: 140 }}
            onChange={(event) => {
              setSkuCode(event.target.value);
              setPage(1);
            }}
          />
          <Input
            allowClear
            placeholder="商品名称"
            value={productName}
            style={{ width: 140 }}
            onChange={(event) => {
              setProductName(event.target.value);
              setPage(1);
            }}
          />
          <AppRangePicker
            key={tenantId ?? 'none'}
            placeholder={['创建开始', '创建结束']}
            onChange={(dates) => {
              const { from, to } = rangeToDateTimes(dates);
              setCreatedRange(from && to ? [from, to] : null);
              setPage(1);
            }}
          />
        </div>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          loading={listQuery.isLoading}
          pagination={{
            current: page,
            pageSize,
            total: listQuery.data?.total ?? 0,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
