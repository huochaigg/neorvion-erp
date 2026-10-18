import {
  ApiError,
  canApprovePurchaseOrder,
  canCancelPurchaseOrder,
  canEditPurchaseOrder,
  canRejectPurchaseOrder,
  canSubmitPurchaseOrder,
  DEFAULT_PAGE_SIZE,
  formatPurchaseAmount,
  PERMISSION_CODE,
  PURCHASE_ORDER_STATUS,
  PURCHASE_ORDER_STATUS_OPTIONS,
  purchaseOrdersQueryKey,
  purchaseOrderStatusLabel,
  SUPPLIER_STATUS,
  suppliersQueryKey,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type PurchaseOrderListItem,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  approvePurchaseOrder,
  cancelPurchaseOrder,
  fetchPurchaseOrders,
  rejectPurchaseOrder,
  submitPurchaseOrder,
} from '@/api/purchase-orders';
import { fetchSuppliers } from '@/api/suppliers';
import { fetchWarehouses } from '@/api/warehouses';
import { AppRangePicker } from '@/components/AppDatePicker';
import { ActionCell, AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDate, formatDateTime, rangeToDates, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

function statusTag(status: string) {
  const color =
    status === PURCHASE_ORDER_STATUS.pendingApproval
      ? 'processing'
      : status === PURCHASE_ORDER_STATUS.waitingReceipt
        ? 'blue'
        : status === PURCHASE_ORDER_STATUS.rejected
          ? 'warning'
          : status === PURCHASE_ORDER_STATUS.cancelled
            ? 'default'
            : 'default';
  return <Tag color={color}>{purchaseOrderStatusLabel(status)}</Tag>;
}

export function PurchaseListPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { tenantId } = usePermissions();
  const [q, setQ] = useState('');
  const [keyword, setKeyword] = useState('');
  const [supplierId, setSupplierId] = useState<number | undefined>();
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [createdRange, setCreatedRange] = useState<[string, string] | null>(null);
  const [expectedRange, setExpectedRange] = useState<[string, string] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setQ('');
    setKeyword('');
    setSupplierId(undefined);
    setWarehouseId(undefined);
    setStatus(undefined);
    setCreatedRange(null);
    setExpectedRange(null);
    setPage(1);
  }, [tenantId]);

  const filters = {
    q: keyword,
    supplierId,
    warehouseId,
    status,
    createdFrom: createdRange?.[0],
    createdTo: createdRange?.[1],
    expectedFrom: expectedRange?.[0],
    expectedTo: expectedRange?.[1],
    page,
    pageSize,
  };

  const listQuery = useQuery({
    queryKey: purchaseOrdersQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchPurchaseOrders(filters, signal),
    enabled: tenantId != null,
  });

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

  const columns: ColumnsType<PurchaseOrderListItem> = [
    {
      title: '采购单号',
      dataIndex: 'order_no',
      key: 'order_no',
      width: 160,
      render: (value: string) => <CodeCell value={value} />,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      width: 180,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '仓库',
      dataIndex: 'warehouse_name',
      key: 'warehouse_name',
      width: 160,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    { title: 'SKU 数', dataIndex: 'sku_count', key: 'sku_count', width: 90 },
    { title: '采购数量', dataIndex: 'total_quantity', key: 'total_quantity', width: 100 },
    {
      title: '金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 120,
      render: (value: number | null) => formatPurchaseAmount(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (value: string) => statusTag(value),
    },
    {
      title: '预计到货日期',
      dataIndex: 'expected_arrival_date',
      key: 'expected_arrival_date',
      width: 140,
      render: (value: string | null) => formatDate(value),
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
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <ActionCell>
          <Button type="link" size="small" onClick={() => navigate(`/purchases/${record.id}`)}>
            详情
          </Button>
          {canEditPurchaseOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.purchaseUpdate}>
              <Button type="link" size="small" onClick={() => navigate(`/purchases/${record.id}/edit`)}>
                编辑
              </Button>
            </Can>
          ) : null}
          {canSubmitPurchaseOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.purchaseSubmit}>
              <Button type="link" size="small" onClick={() => submitMutation.mutate(record.id)}>
                {record.status === PURCHASE_ORDER_STATUS.rejected ? '重新提交' : '提交审核'}
              </Button>
            </Can>
          ) : null}
          {canApprovePurchaseOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.purchaseAudit}>
              <Button type="link" size="small" onClick={() => approveMutation.mutate(record.id)}>
                通过
              </Button>
            </Can>
          ) : null}
          {canRejectPurchaseOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.purchaseAudit}>
              <Button
                type="link"
                size="small"
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
                        await rejectPurchaseOrder(record.id, text);
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
          {canCancelPurchaseOrder(record.status) ? (
            <Can permission={PERMISSION_CODE.purchaseCancel}>
              <Button
                type="link"
                size="small"
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
                        await cancelPurchaseOrder(record.id, reason.trim() || null);
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
        </ActionCell>
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

  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '采购单'}
        description={props.description ?? '创建草稿、提交审核、审核通过后进入待收货。本版不增加库存。'}
        extra={
          <Can permission={PERMISSION_CODE.purchaseCreate}>
            <Button type="primary" onClick={() => navigate('/purchases/create')}>
              新建采购单
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input
            className="w-44!"
            placeholder="采购单号"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            onPressEnter={() => {
              setKeyword(q.trim());
              setPage(1);
            }}
            allowClear
          />
          <Select
            className="w-48!"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="供应商"
            value={supplierId}
            onChange={(value) => {
              setSupplierId(value);
              setPage(1);
            }}
            options={supplierOptions}
          />
          <Select
            className="w-44!"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="仓库"
            value={warehouseId}
            onChange={(value) => {
              setWarehouseId(value);
              setPage(1);
            }}
            options={warehouseOptions}
          />
          <Select
            className="w-36"
            allowClear
            placeholder="状态"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={PURCHASE_ORDER_STATUS_OPTIONS}
          />
          <AppRangePicker
            placeholder={['创建日期起', '创建日期止']}
            onChange={(dates) => {
              const { from, to } = rangeToDateTimes(dates);
              setCreatedRange(from && to ? [from, to] : null);
              setPage(1);
            }}
          />
          <AppRangePicker
            placeholder={['预计到货起', '预计到货止']}
            onChange={(dates) => {
              const { from, to } = rangeToDates(dates);
              setExpectedRange(from && to ? [from, to] : null);
              setPage(1);
            }}
          />
          <Button
            onClick={() => {
              setKeyword(q.trim());
              setPage(1);
            }}
          >
            查询
          </Button>
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
