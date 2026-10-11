import {
  DEFAULT_PAGE_SIZE,
  purchaseReturnOutboundsQueryKey,
  purchaseReturnOutboundStatusLabel,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchPurchaseReturnOutbounds } from '@/api/purchase-return-outbounds';
import { AppTable } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function PurchaseReturnOutboundListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { q, status, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: purchaseReturnOutboundsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchPurchaseReturnOutbounds(filters, signal),
    enabled: tenantId != null,
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '出库单号', dataIndex: 'outbound_no', width: 160 },
    { title: '采购退货单', dataIndex: 'purchase_return_no', width: 160 },
    { title: '原采购单', dataIndex: 'purchase_order_no', width: 150 },
    { title: '供应商', dataIndex: 'supplier_name', width: 140 },
    { title: '仓库', dataIndex: 'warehouse_name', width: 120 },
    { title: '数量', dataIndex: 'total_quantity', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{purchaseReturnOutboundStatusLabel(value)}</Tag>,
    },
    {
      title: '确认时间',
      dataIndex: 'confirmed_at',
      width: 170,
      render: (value: string | null) => (value ? formatDateTime(value) : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_, row) => (
        <Button type="link" onClick={() => navigate(`/purchase-return-outbounds/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '采购退货出库'} description={props.description} />
      <ListToolbar>
        <Input
          allowClear
          placeholder="出库单号 / 退货单号"
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
          options={[
            { value: 'DRAFT', label: '草稿' },
            { value: 'CONFIRMED', label: '已确认' },
            { value: 'CANCELLED', label: '已取消' },
          ]}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
          style={{ width: 140 }}
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
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
