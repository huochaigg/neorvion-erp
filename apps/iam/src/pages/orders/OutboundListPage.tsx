import { DEFAULT_PAGE_SIZE, outboundOrdersQueryKey } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchOutboundOrders } from '@/api/outbound-orders';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

const STATUS_LABEL: Record<string, string> = {
  PENDING_PICKING: '待拣货',
  PICKED: '已拣货',
  CONFIRMED: '已出库',
  CANCELLED: '已取消',
};

export function OutboundListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<string>();
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { q, status, createdFrom, createdTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: outboundOrdersQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchOutboundOrders(filters, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '出库单号', dataIndex: 'outbound_no', width: 160 },
    { title: '订单号', dataIndex: 'sales_order_no', width: 160 },
    { title: '客户', dataIndex: 'customer_name', width: 140 },
    { title: '仓库', dataIndex: 'warehouse_name', width: 140 },
    { title: 'SKU 数', dataIndex: 'sku_count', width: 90 },
    { title: '计划', dataIndex: 'planned_quantity', width: 80 },
    { title: '拣货', dataIndex: 'picked_quantity', width: 80 },
    { title: '出库', dataIndex: 'outbound_quantity', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{STATUS_LABEL[value] ?? value}</Tag>,
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
        <Button type="link" onClick={() => navigate(`/outbound-orders/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '销售出库'}
        description={props.description ?? '拣货不扣库存。确认出库后实际库存和预占同时减少。'}
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="出库单号"
            style={{ width: 200 }}
            onSearch={(value) => {
              setPage(1);
              setQ(value.trim());
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            options={Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))}
            onChange={(value) => {
              setPage(1);
              setStatus(value);
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
