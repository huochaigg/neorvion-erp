import {
  DEFAULT_PAGE_SIZE,
  purchaseReceiptsQueryKey,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchPurchaseReceipts } from '@/api/purchase-receipts';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

const STATUS_LABEL: Record<string, string> = {
  DRAFT: '草稿',
  CONFIRMED: '已确认',
  CANCELLED: '已作废',
};

export function PurchaseReceiptListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<string>();
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { q, status, createdFrom, createdTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: purchaseReceiptsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchPurchaseReceipts(filters, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '收货单号', dataIndex: 'receipt_no', width: 160 },
    { title: '采购单', dataIndex: 'purchase_order_no', width: 160 },
    { title: '供应商', dataIndex: 'supplier_name', width: 160 },
    { title: '仓库', dataIndex: 'warehouse_name', width: 140 },
    { title: 'SKU 数', dataIndex: 'sku_count', width: 90 },
    { title: '本次收货', dataIndex: 'total_received', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{STATUS_LABEL[value] ?? value}</Tag>,
    },
    { title: '收货人', dataIndex: 'received_by_name', width: 120 },
    {
      title: '收货时间',
      dataIndex: 'received_at',
      width: 170,
      render: (value: string | null) => formatDateTime(value),
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
        <Button type="link" onClick={() => navigate(`/purchase-receipts/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '采购收货'} description={props.description} />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="收货单号"
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
