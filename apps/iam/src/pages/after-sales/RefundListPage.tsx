import {
  ApiError,
  canConfirmRefundRecord,
  canFailRefundRecord,
  DEFAULT_PAGE_SIZE,
  formatSalesAmount,
  PERMISSION_CODE,
  REFUND_RECORD_STATUS_OPTIONS,
  refundRecordStatusLabel,
  refundsQueryKey,
} from '@neorvion/shared';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App, Button, Input, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { confirmRefund, failRefund, fetchRefunds } from '@/api/refunds';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable } from '@/components/AppTable';
import { Can } from '@/components/Can';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function RefundListPage(props: PageProps) {
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
    queryKey: refundsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchRefunds(filters, signal),
    enabled: tenantId != null,
  });
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'refunds'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'refund'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sales'] });
    void queryClient.invalidateQueries({ queryKey: ['tenant', tenantId, 'after-sale'] });
  };
  const confirmMutation = useMutation({
    mutationFn: ({ id, external }: { id: number; external?: string }) =>
      confirmRefund(id, { external_reference_no: external || null }),
    onSuccess: () => {
      message.success('已确认退款成功');
      invalidate();
    },
    onError: (error: unknown) => message.error(error instanceof ApiError ? error.message : '确认失败'),
  });
  const columns: ColumnsType<NonNullable<typeof query.data>['items'][number]> = [
    { title: '退款编号', dataIndex: 'refund_no', width: 160 },
    { title: '售后单', dataIndex: 'after_sale_no', width: 160 },
    { title: '销售订单', dataIndex: 'sales_order_no', width: 160 },
    { title: '客户', dataIndex: 'customer_name', width: 140 },
    {
      title: '退款金额',
      dataIndex: 'amount',
      width: 110,
      render: (value: number) => formatSalesAmount(value),
    },
    {
      title: '退款状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => <Tag>{refundRecordStatusLabel(value)}</Tag>,
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
      title: '退款时间',
      dataIndex: 'refunded_at',
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
      width: 180,
      fixed: 'right',
      render: (_, row) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/after-sales/${row.after_sale_order_id}`)}>
            售后
          </Button>
          {canConfirmRefundRecord(row.status) ? (
            <Can permission={PERMISSION_CODE.refundConfirm}>
              <Button
                type="link"
                loading={confirmMutation.isPending}
                onClick={() => {
                  let external = '';
                  modal.confirm({
                    title: '确认退款成功',
                    content: (
                      <Input
                        placeholder="外部退款流水号（可选）"
                        onChange={(event) => {
                          external = event.target.value;
                        }}
                      />
                    ),
                    onOk: () => confirmMutation.mutateAsync({ id: row.id, external: external.trim() }),
                  });
                }}
              >
                确认
              </Button>
            </Can>
          ) : null}
          {canFailRefundRecord(row.status) ? (
            <Can permission={PERMISSION_CODE.refundConfirm}>
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
                        maxLength={255}
                        placeholder="失败原因"
                        onChange={(event) => {
                          reason = event.target.value;
                        }}
                      />
                    ),
                    onOk: async () => {
                      if (!reason.trim()) {
                        message.error('请填写失败原因');
                        return Promise.reject(new Error('reason required'));
                      }
                      try {
                        await failRefund(row.id, { failure_reason: reason.trim() });
                        message.success('已标记失败，可以再次登记退款');
                        invalidate();
                      } catch (error) {
                        message.error(error instanceof ApiError ? error.message : '标记失败未成功');
                        return Promise.reject(new Error('fail refund'));
                      }
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
      <PageHeader title={props.title ?? '退款记录'} description={props.description} />
      <ListToolbar>
        <div className="flex flex-wrap gap-2">
          <Input.Search
            allowClear
            placeholder="退款编号 / 售后单 / 销售订单"
            style={{ width: 260 }}
            onSearch={(value) => {
              setPage(1);
              setQ(value.trim());
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 140 }}
            options={REFUND_RECORD_STATUS_OPTIONS}
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
