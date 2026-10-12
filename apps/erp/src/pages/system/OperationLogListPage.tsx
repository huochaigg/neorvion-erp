import {
  DEFAULT_PAGE_SIZE,
  OPERATION_RESULT_LABEL,
  operationLogsQueryKey,
  type OperationLog,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchOperationLogs } from '@/api/operation-logs';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable, EllipsisCell } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function OperationLogListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [module, setModule] = useState<string>();
  const [action, setAction] = useState<string>();
  const [result, setResult] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [occurredFrom, setOccurredFrom] = useState<string>();
  const [occurredTo, setOccurredTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = { module, action, result, keyword, occurredFrom, occurredTo, page, pageSize: DEFAULT_PAGE_SIZE };
  const query = useQuery({
    queryKey: operationLogsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchOperationLogs(filters, signal),
    enabled: tenantId != null,
  });

  const columns: ColumnsType<OperationLog> = [
    {
      title: '时间',
      dataIndex: 'occurred_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
    { title: '操作人', dataIndex: 'operator_user_id', width: 90 },
    { title: '模块', dataIndex: 'module', width: 120 },
    { title: '动作', dataIndex: 'action', width: 110 },
    {
      title: '资源',
      key: 'resource',
      width: 200,
      render: (_, row) => row.resource_name || `${row.resource_type ?? '-'}${row.resource_id ? `#${row.resource_id}` : ''}`,
    },
    {
      title: '请求',
      key: 'request',
      width: 200,
      render: (_, row) => (row.request_method ? `${row.request_method} ${row.request_path ?? ''}` : '-'),
    },
    {
      title: '结果',
      dataIndex: 'result',
      width: 90,
      render: (value: string) => (
        <Tag color={value === 'SUCCESS' ? 'green' : 'red'}>{OPERATION_RESULT_LABEL[value] ?? value}</Tag>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      width: 220,
      render: (value: string | null) => <EllipsisCell value={value || '-'} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_, row) => (
        <Button type="link" onClick={() => navigate(`/system/operation-logs/${row.id}`)}>
          详情
        </Button>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '操作日志'} description={props.description} />
      <ListToolbar>
        <Space wrap>
          <Input
            allowClear
            placeholder="描述 / 请求ID"
            value={keyword}
            onChange={(event) => {
              setKeyword(event.target.value);
              setPage(1);
            }}
            style={{ width: 180 }}
          />
          <Input
            allowClear
            placeholder="模块"
            value={module}
            onChange={(event) => {
              setModule(event.target.value || undefined);
              setPage(1);
            }}
            style={{ width: 140 }}
          />
          <Input
            allowClear
            placeholder="动作"
            value={action}
            onChange={(event) => {
              setAction(event.target.value || undefined);
              setPage(1);
            }}
            style={{ width: 120 }}
          />
          <Select
            allowClear
            placeholder="结果"
            value={result}
            style={{ width: 110 }}
            options={[
              { value: 'SUCCESS', label: '成功' },
              { value: 'FAILED', label: '失败' },
            ]}
            onChange={(value) => {
              setResult(value);
              setPage(1);
            }}
          />
          <AppRangePicker
            onChange={(dates) => {
              const range = rangeToDateTimes(dates);
              setOccurredFrom(range.from);
              setOccurredTo(range.to);
              setPage(1);
            }}
          />
        </Space>
      </ListToolbar>
      <ListTableArea>
        <AppTable
          rowKey="id"
          loading={query.isPending}
          columns={columns}
          dataSource={query.data?.items ?? []}
          pagination={{
            current: page,
            total: query.data?.total ?? 0,
            pageSize: DEFAULT_PAGE_SIZE,
            onChange: setPage,
          }}
        />
      </ListTableArea>
    </ListPageContainer>
  );
}
