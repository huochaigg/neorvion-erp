import {
  DEFAULT_PAGE_SIZE,
  RETURN_ORDER_STATUS_OPTIONS,
  returnOrdersQueryKey,
  returnOrderStatusLabel,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchReturnOrders } from '@/api/return-orders';
import { fetchWarehouses } from '@/api/warehouses';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function ReturnOrderListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [warehouseId, setWarehouseId] = useState<number>();
  const [status, setStatus] = useState<string>();
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { q, warehouseId, status, createdFrom, createdTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: returnOrdersQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchReturnOrders(filters, signal),
    enabled: tenantId != null,
  });
  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '退货单号', dataIndex: 'return_no', width: 160 },
    { title: '售后单', dataIndex: 'after_sale_no', width: 160 },
    { title: '销售订单', dataIndex: 'sales_order_no', width: 160 },
    { title: '客户', dataIndex: 'customer_name', width: 140 },
    { title: '退货仓库', dataIndex: 'warehouse_name', width: 140 },
    { title: '预期数量', dataIndex: 'expected_quantity', width: 100 },
    { title: '已收数量', dataIndex: 'received_quantity', width: 100 },
    { title: '已入库数量', dataIndex: 'inbound_quantity', width: 110 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag>{returnOrderStatusLabel(value)}</Tag>,
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
        <Button type="link" onClick={() => navigate(`/return-orders/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '退货单'} description={props.description} />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="退货单号 / 售后单 / 销售订单"
            style={{ width: 240 }}
            onSearch={(value) => {
              setPage(1);
              setQ(value.trim());
            }}
          />
          <Select
            allowClear
            placeholder="仓库"
            style={{ width: 180 }}
            options={(warehouseQuery.data?.items ?? []).map((item) => ({
              value: item.id,
              label: item.name,
            }))}
            onChange={(value) => {
              setPage(1);
              setWarehouseId(value);
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            options={RETURN_ORDER_STATUS_OPTIONS}
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
