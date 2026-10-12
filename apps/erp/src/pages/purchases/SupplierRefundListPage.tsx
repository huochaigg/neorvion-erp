import {
  ApiError,
  canConfirmSupplierRefund,
  DEFAULT_PAGE_SIZE,
  formatPurchaseAmount,
  PERMISSION_CODE,
  supplierRefundRecordStatusLabel,
  supplierRefundsQueryKey,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { confirmSupplierRefund, failSupplierRefund, fetchSupplierRefunds } from '@/api/supplier-refunds';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function SupplierRefundListPage(props: PageProps) {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const queryClient = useQueryClient();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<string>();
  const [createdFrom, setCreatedFrom] = useState<string>();
  const [createdTo, setCreatedTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { q, status, createdFrom, createdTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: supplierRefundsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchSupplierRefunds(filters, signal),
    enabled: tenantId != null,
  });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'supplier-refunds'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-return'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'purchase-returns'] });
  };
  const confirmMutation = useMutation({
    mutationFn: ({ id, external }: { id: number; external?: string }) =>
      confirmSupplierRefund(id, { external_reference_no: external || null }),
    onSuccess: () => {
      message.success('已确认供应商退款成功');
      invalidate();
    },
    onError: (error: unknown) => message.error(error instanceof ApiError ? error.message : '确认失败'),
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '退款编号', dataIndex: 'refund_no', width: 160 },
    { title: '采购退货单', dataIndex: 'purchase_return_no', width: 160 },
    { title: '供应商', dataIndex: 'supplier_name', width: 140 },
    {
      title: '退款金额',
      dataIndex: 'amount',
      width: 110,
      render: (value: number) => formatPurchaseAmount(value),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{supplierRefundRecordStatusLabel(value)}</Tag>,
    },
    {
      title: '外部流水号',
      dataIndex: 'external_reference_no',
      width: 160,
      render: (value: string | null) => value || '-',
    },
    {
      title: '失败原因',
      dataIndex: 'failure_reason',
      width: 180,
      render: (value: string | null) => value || '-',
    },
    {
      title: '到账时间',
      dataIndex: 'received_at',
      width: 170,
      render: (value: string | null) => (value ? formatDateTime(value) : '-'),
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
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/purchase-returns/${row.purchase_return_id}`)}>
            退货单
          </Button>
          {canConfirmSupplierRefund(row.status) ? (
            <Can permission={PERMISSION_CODE.supplierRefundConfirm}>
              <Button type="link" onClick={() => confirmMutation.mutate({ id: row.id })}>
                成功
              </Button>
              <Button
                type="link"
                danger
                onClick={() => {
                  let reason = '';
                  modal.confirm({
                    title: '标记退款失败',
                    content: (
                      <Input.TextArea
                        rows={3}
                        onChange={(event) => {
                          reason = event.target.value;
                        }}
                      />
                    ),
                    onOk: async () => {
                      if (!reason.trim()) {
                        message.error('请填写失败原因');
                        return Promise.reject();
                      }
                      await failSupplierRefund(row.id, { failure_reason: reason.trim() });
                      message.success('已标记失败');
                      invalidate();
                    },
                  });
                }}
              >
                失败
              </Button>
            </Can>
          ) : null}
        </Space>
      ),
    },
  ];
  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '供应商退款'} description={props.description} />
      <ListToolbar>
        <Space>
          <Input
            allowClear
            placeholder="退款编号 / 退货单号 / 供应商"
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            style={{ width: 260 }}
          />
          <Select
            allowClear
            placeholder="状态"
            value={status}
            options={[
              { value: 'PENDING', label: '待确认' },
              { value: 'SUCCESS', label: '成功' },
              { value: 'FAILED', label: '失败' },
            ]}
            onChange={(value) => {
              setStatus(value);
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
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          scroll={{ x: 1700 }}
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
