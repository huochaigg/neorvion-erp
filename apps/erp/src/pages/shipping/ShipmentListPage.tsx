import {
  DEFAULT_PAGE_SIZE,
  SHIPMENT_STATUS_OPTIONS,
  shipmentStatusLabel,
  shipmentsQueryKey,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchShipments } from '@/api/shipments';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function ShipmentListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<string>();
  const [shippedFrom, setShippedFrom] = useState<string>();
  const [shippedTo, setShippedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { q, status, shippedFrom, shippedTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: shipmentsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchShipments(filters, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '物流单号', dataIndex: 'shipment_no', width: 160 },
    { title: '订单号', dataIndex: 'sales_order_no', width: 160 },
    { title: '出库单', dataIndex: 'outbound_no', width: 160 },
    { title: '客户', dataIndex: 'customer_name', width: 140 },
    { title: '物流商', dataIndex: 'carrier_name', width: 140 },
    { title: '运单号', dataIndex: 'tracking_no', width: 160, render: (value: string | null) => value || '-' },
    { title: 'SKU 数', dataIndex: 'sku_count', width: 90 },
    { title: '商品数量', dataIndex: 'total_quantity', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{shipmentStatusLabel(value)}</Tag>,
    },
    {
      title: '发货时间',
      dataIndex: 'shipped_at',
      width: 170,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '签收时间',
      dataIndex: 'delivered_at',
      width: 170,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      fixed: 'right',
      render: (_, row) => (
        <Button type="link" onClick={() => navigate(`/shipments/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '物流单'} description={props.description} />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="物流单号 / 订单号 / 出库单 / 运单号"
            style={{ width: 280 }}
            onSearch={(value) => {
              setPage(1);
              setQ(value.trim());
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            options={SHIPMENT_STATUS_OPTIONS}
            onChange={(value) => {
              setPage(1);
              setStatus(value);
            }}
          />
          <AppRangePicker
            onChange={(dates) => {
              const { from, to } = rangeToDateTimes(dates);
              setPage(1);
              setShippedFrom(from);
              setShippedTo(to);
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
            onChange: (next) => setPage(next),
          }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
