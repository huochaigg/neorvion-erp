import {
  AFTER_SALE_REFUND_STATUS_OPTIONS,
  AFTER_SALE_STATUS_OPTIONS,
  AFTER_SALE_TYPE_OPTIONS,
  afterSaleRefundStatusLabel,
  afterSaleStatusLabel,
  afterSalesQueryKey,
  afterSaleTypeLabel,
  DEFAULT_PAGE_SIZE,
  formatSalesAmount,
  PERMISSION_CODE,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAfterSales } from '@/api/after-sales';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function AfterSaleListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [type, setType] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [refundStatus, setRefundStatus] = useState<string>();
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { q, type, status, refundStatus, createdFrom, createdTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: afterSalesQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchAfterSales(filters, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '售后单号', dataIndex: 'after_sale_no', width: 160 },
    { title: '销售订单', dataIndex: 'sales_order_no', width: 160 },
    { title: '客户', dataIndex: 'customer_name', width: 140 },
    {
      title: '类型',
      dataIndex: 'type',
      width: 110,
      render: (value: string) => afterSaleTypeLabel(value),
    },
    { title: '退货数量', dataIndex: 'return_quantity', width: 100 },
    {
      title: '申请退款',
      dataIndex: 'requested_refund_amount',
      width: 110,
      render: (value: number) => formatSalesAmount(value),
    },
    {
      title: '批准退款',
      dataIndex: 'approved_refund_amount',
      width: 110,
      render: (value: number | null) => formatSalesAmount(value),
    },
    {
      title: '售后状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag>{afterSaleStatusLabel(value)}</Tag>,
    },
    {
      title: '退款状态',
      dataIndex: 'refund_status',
      width: 110,
      render: (value: string) => afterSaleRefundStatusLabel(value),
    },
    {
      title: '申请时间',
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
        <Button type="link" onClick={() => navigate(`/after-sales/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '售后单'}
        description={props.description}
        extra={
          <Can permission={PERMISSION_CODE.afterSaleCreate}>
            <Button onClick={() => navigate('/orders/list')}>从销售订单申请</Button>
          </Can>
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="售后单号 / 销售订单 / 客户"
            style={{ width: 240 }}
            onSearch={(value) => {
              setPage(1);
              setQ(value.trim());
            }}
          />
          <Select
            allowClear
            placeholder="类型"
            style={{ width: 140 }}
            options={AFTER_SALE_TYPE_OPTIONS}
            onChange={(value) => {
              setPage(1);
              setType(value);
            }}
          />
          <Select
            allowClear
            placeholder="售后状态"
            style={{ width: 140 }}
            options={AFTER_SALE_STATUS_OPTIONS}
            onChange={(value) => {
              setPage(1);
              setStatus(value);
            }}
          />
          <Select
            allowClear
            placeholder="退款状态"
            style={{ width: 140 }}
            options={AFTER_SALE_REFUND_STATUS_OPTIONS}
            onChange={(value) => {
              setPage(1);
              setRefundStatus(value);
            }}
          />
          <AppRangePicker
            onChange={(dates) => {
              const { from, to } = rangeToDateTimes(dates);
              setPage(1);
              setCreatedFrom(from);
              setCreatedTo(to);
            }}
          />
        </div>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          columns={columns}
          dataSource={query.data?.items ?? []}
          loading={query.isLoading}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total: query.data?.total ?? 0,
            onChange: setPage,
          }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
