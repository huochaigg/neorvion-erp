import {
  DEFAULT_PAGE_SIZE,
  INVENTORY_TRANSACTION_TYPE_OPTIONS,
  inventoryTransactionTypeLabel,
  inventoryTransactionsQueryKey,
  WAREHOUSE_STATUS,
  warehousesQueryKey,
  type InventoryTransaction,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchInventoryTransactions } from '@/api/inventory';
import { fetchWarehouses } from '@/api/warehouses';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable, CodeCell, EllipsisCell } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { usePermissions } from '@/hooks/usePermissions';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';

export function InventoryTransactionsPage(props: PageProps) {
  const { tenantId } = usePermissions();
  const [searchParams] = useSearchParams();
  const inventoryIdParam = Number(searchParams.get('inventoryId') ?? '');
  const inventoryId = Number.isInteger(inventoryIdParam) && inventoryIdParam > 0 ? inventoryIdParam : undefined;
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const [skuKeyword, setSkuKeyword] = useState('');
  const [skuId, setSkuId] = useState<number | undefined>();
  const [txType, setTxType] = useState<string | undefined>();
  const [range, setRange] = useState<[string, string] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setWarehouseId(undefined);
    setSkuKeyword('');
    setSkuId(undefined);
    setTxType(undefined);
    setRange(null);
    setPage(1);
  }, [tenantId]);

  const warehouseQuery = useQuery({
    queryKey: warehousesQueryKey(tenantId, { status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }),
    queryFn: ({ signal }) =>
      fetchWarehouses({ status: WAREHOUSE_STATUS.active, page: 1, pageSize: 100 }, signal),
    enabled: tenantId != null,
  });

  const filters = {
    warehouseId,
    skuId,
    inventoryId,
    type: txType,
    createdFrom: range?.[0],
    createdTo: range?.[1],
    page,
    pageSize,
  };

  const listQuery = useQuery({
    queryKey: inventoryTransactionsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchInventoryTransactions(filters, signal),
    enabled: tenantId != null,
  });

  const warehouseOptions = useMemo(
    () => (warehouseQuery.data?.items ?? []).map((item) => ({ value: item.id, label: item.name })),
    [warehouseQuery.data],
  );

  const columns: ColumnsType<InventoryTransaction> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '仓库',
      dataIndex: 'warehouse_name',
      key: 'warehouse_name',
      width: 160,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '商品',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 200,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: 'SKU',
      dataIndex: 'sku_code',
      key: 'sku_code',
      width: 180,
      render: (value: string) => <CodeCell value={value} />,
    },
    {
      title: 'SKU 名称',
      dataIndex: 'sku_name',
      key: 'sku_name',
      width: 140,
      render: (value: string) => <EllipsisCell value={value} />,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 110,
      render: (value: string) => inventoryTransactionTypeLabel(value),
    },
    { title: '变化', dataIndex: 'change_quantity', key: 'change_quantity', width: 80 },
    {
      title: '实际库存',
      key: 'qty',
      width: 130,
      render: (_, record) => `${record.before_quantity} → ${record.after_quantity}`,
    },
    {
      title: '预占',
      key: 'reserved',
      width: 130,
      render: (_, record) => `${record.before_reserved_quantity} → ${record.after_reserved_quantity}`,
    },
    {
      title: '操作人',
      dataIndex: 'operator_name',
      key: 'operator_name',
      width: 110,
      render: (value: string | null) => <EllipsisCell value={value || '-'} />,
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      width: 200,
      render: (value: string | null) => <EllipsisCell value={value || '-'} />,
    },
    {
      title: '关联单据',
      key: 'ref',
      width: 160,
      render: (_, record) => (
        <CodeCell
          value={
            record.reference_type || record.reference_id
              ? `${record.reference_type ?? '-'} #${record.reference_id ?? '-'}`
              : '-'
          }
        />
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader
        title={props.title ?? '库存流水'}
        description={
          props.description ??
          '流水只追加、不修改。纠错请做新的库存调整。V5 尚无采购/订单单据，关联单号通常为空。'
        }
      />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
        <Select
          className="w-44!"
          allowClear
          placeholder="仓库"
          value={warehouseId}
          onChange={(value) => {
            setWarehouseId(value);
            setPage(1);
          }}
          options={warehouseOptions}
        />
        <Input
          className="w-40!"
          placeholder="SKU ID（精确）"
          value={skuKeyword}
          onChange={(event) => setSkuKeyword(event.target.value)}
          onPressEnter={() => {
            const parsed = Number(skuKeyword.trim());
            setSkuId(Number.isInteger(parsed) && parsed > 0 ? parsed : undefined);
            setPage(1);
          }}
          allowClear
        />
        <Select
          className="w-40"
          allowClear
          placeholder="类型"
          value={txType}
          onChange={(value) => {
            setTxType(value);
            setPage(1);
          }}
          options={INVENTORY_TRANSACTION_TYPE_OPTIONS}
        />
        <AppRangePicker
          onChange={(dates) => {
            const { from, to } = rangeToDateTimes(dates);
            setRange(from && to ? [from, to] : null);
            setPage(1);
          }}
        />
        <Button
          onClick={() => {
            const parsed = Number(skuKeyword.trim());
            setSkuId(Number.isInteger(parsed) && parsed > 0 ? parsed : undefined);
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
