import {
  DEFAULT_PAGE_SIZE,
  PERMISSION_CODE,
  STOCKTAKE_STATUS_OPTIONS,
  stocktakeScopeLabel,
  stocktakeStatusLabel,
  stocktakesQueryKey,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchStocktakes } from '@/api/stocktakes';
import { fetchWarehouses } from '@/api/warehouses';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function StocktakeListPage(props: PageProps) {
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
    queryKey: stocktakesQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchStocktakes(filters, signal),
    enabled: tenantId != null,
  });
  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '盘点单号', dataIndex: 'stocktake_no', width: 160 },
    { title: '仓库', dataIndex: 'warehouse_name', width: 140 },
    {
      title: '盘点范围',
      dataIndex: 'scope',
      width: 120,
      render: (value: string) => stocktakeScopeLabel(value),
    },
    { title: 'SKU 数量', dataIndex: 'sku_count', width: 100 },
    { title: '差异 SKU 数', dataIndex: 'difference_sku_count', width: 120 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag>{stocktakeStatusLabel(value)}</Tag>,
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
        <Button type="link" onClick={() => navigate(`/stocktakes/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '库存盘点'}
        description={props.description}
        extra={
          <Can permission={PERMISSION_CODE.stocktakeCreate}>
            <Button type="primary" onClick={() => navigate('/stocktakes/create')}>
              新建盘点
            </Button>
          </Can>
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="盘点单号"
            style={{ width: 200 }}
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
            options={STOCKTAKE_STATUS_OPTIONS}
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
