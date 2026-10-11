import {
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  PURCHASE_RETURN_REFUND_STATUS_OPTIONS,
  PURCHASE_RETURN_SETTLEMENT_OPTIONS,
  PURCHASE_RETURN_STATUS_OPTIONS,
  formatPurchaseAmount,
  purchaseReturnRefundStatusLabel,
  purchaseReturnsQueryKey,
  purchaseReturnStatusLabel,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchPurchaseReturns } from '@/api/purchase-returns';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function PurchaseReturnListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<string>();
  const [settlementType, setSettlementType] = useState<string>();
  const [refundStatus, setRefundStatus] = useState<string>();
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = {
    q,
    status,
    settlementType,
    refundStatus,
    createdFrom,
    createdTo,
    page,
    pageSize: DEFAULT_PAGE_SIZE,
  };
  const query = useQuery({
    queryKey: purchaseReturnsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchPurchaseReturns(filters, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '退货单号', dataIndex: 'purchase_return_no', width: 160 },
    { title: '原采购单', dataIndex: 'purchase_order_no', width: 150 },
    { title: '供应商', dataIndex: 'supplier_name', width: 140 },
    { title: '仓库', dataIndex: 'warehouse_name', width: 120 },
    { title: 'SKU 数', dataIndex: 'sku_count', width: 80 },
    { title: '申请退货', dataIndex: 'requested_return_quantity', width: 100 },
    {
      title: '批准数量',
      dataIndex: 'approved_return_quantity',
      width: 90,
      render: (value: number | null) => value ?? '-',
    },
    { title: '已实际退货', dataIndex: 'returned_quantity', width: 110 },
    {
      title: '申请退款',
      dataIndex: 'requested_refund_amount',
      width: 110,
      render: (value: number) => formatPurchaseAmount(value),
    },
    {
      title: '批准退款',
      dataIndex: 'approved_refund_amount',
      width: 110,
      render: (value: number | null) => formatPurchaseAmount(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag>{purchaseReturnStatusLabel(value)}</Tag>,
    },
    {
      title: '退款状态',
      dataIndex: 'refund_status',
      width: 110,
      render: (value: string) => purchaseReturnRefundStatusLabel(value),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      fixed: 'right',
      render: (_, row) => (
        <Button type="link" onClick={() => navigate(`/purchase-returns/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '采购退货'}
        description={props.description}
        extra={
          <Can permission={PERMISSION_CODE.purchaseReturnCreate}>
            <Button type="primary" onClick={() => navigate('/purchases/list')}>
              从采购单创建
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <Input
          allowClear
          placeholder="退货单号 / 采购单号 / 供应商"
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setPage(1);
          }}
          style={{ width: 240 }}
        />
        <Select
          allowClear
          placeholder="状态"
          value={status}
          options={PURCHASE_RETURN_STATUS_OPTIONS}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          style={{ width: 140 }}
        />
        <Select
          allowClear
          placeholder="结算类型"
          value={settlementType}
          options={PURCHASE_RETURN_SETTLEMENT_OPTIONS}
          onChange={(value) => {
            setSettlementType(value);
            setPage(1);
          }}
          style={{ width: 140 }}
        />
        <Select
          allowClear
          placeholder="退款状态"
          value={refundStatus}
          options={PURCHASE_RETURN_REFUND_STATUS_OPTIONS}
          onChange={(value) => {
            setRefundStatus(value);
            setPage(1);
          }}
          style={{ width: 140 }}
        />
        <AppRangePicker
          onChange={(range) => {
            const { from, to } = rangeToDateTimes(range);
            setCreatedFrom(from);
            setCreatedTo(to);
            setPage(1);
          }}
        />
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total: query.data?.total ?? 0,
            onChange: setPage,
          }}
          scroll={{ x: 1760 }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
