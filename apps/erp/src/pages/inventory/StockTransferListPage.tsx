import {
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  STOCK_TRANSFER_STATUS_OPTIONS,
  stockTransferStatusLabel,
  stockTransfersQueryKey,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchStockTransfers } from '@/api/stock-transfers';
import { fetchWarehouses } from '@/api/warehouses';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function StockTransferListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [sourceWarehouseId, setSourceWarehouseId] = useState<number>();
  const [targetWarehouseId, setTargetWarehouseId] = useState<number>();
  const [status, setStatus] = useState<string>();
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = {
    q,
    sourceWarehouseId,
    targetWarehouseId,
    status,
    createdFrom,
    createdTo,
    page,
    pageSize: DEFAULT_PAGE_SIZE,
  };
  const query = useQuery({
    queryKey: stockTransfersQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchStockTransfers(filters, signal),
    enabled: tenantId != null,
  });
  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });
  const warehouseOptions = (warehouseQuery.data?.items ?? []).map((item) => ({
    value: item.id,
    label: item.name,
  }));
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '调拨单号', dataIndex: 'transfer_no', width: 160 },
    { title: '调出仓', dataIndex: 'source_warehouse_name', width: 140 },
    { title: '调入仓', dataIndex: 'target_warehouse_name', width: 140 },
    { title: 'SKU 数量', dataIndex: 'sku_count', width: 100 },
    { title: '调拨总数量', dataIndex: 'total_quantity', width: 110 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag>{stockTransferStatusLabel(value)}</Tag>,
    },
    { title: '创建人', dataIndex: 'created_by_name', width: 120 },
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
        <Button type="link" onClick={() => navigate(`/stock-transfers/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '库存调拨'}
        description={props.description}
        extra={
          <Can permission={PERMISSION_CODE.stockTransferCreate}>
            <Button type="primary" onClick={() => navigate('/stock-transfers/create')}>
              新建调拨
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="调拨单号"
            style={{ width: 200 }}
            onSearch={(value) => {
              setPage(1);
              setQ(value.trim());
            }}
          />
          <Select
            allowClear
            placeholder="调出仓"
            style={{ width: 160 }}
            options={warehouseOptions}
            onChange={(value) => {
              setPage(1);
              setSourceWarehouseId(value);
            }}
          />
          <Select
            allowClear
            placeholder="调入仓"
            style={{ width: 160 }}
            options={warehouseOptions}
            onChange={(value) => {
              setPage(1);
              setTargetWarehouseId(value);
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            options={STOCK_TRANSFER_STATUS_OPTIONS}
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
