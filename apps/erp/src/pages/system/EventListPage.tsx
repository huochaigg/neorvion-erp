import {
  DEFAULT_PAGE_SIZE,
  EVENT_SEVERITY_LABEL,
  EVENT_STATUS_LABEL,
  eventsQueryKey,
  eventBusinessPath,
  eventSeverityLabel,
  type SystemEvent,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Input, Select, Space, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchEvents } from '@/api/events';
import { AppRangePicker } from '@/components/AppDatePicker';
import { AppTable, EllipsisCell } from '@/components/AppTable';
import { ListPageContainer, ListTableArea, ListToolbar } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime, rangeToDateTimes } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

const SEVERITY_COLOR: Record<string, string> = {
  INFO: 'default',
  WARNING: 'gold',
  ERROR: 'red',
  CRITICAL: 'magenta',
};

export function EventListPage(props: PageProps) {
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const [eventType, setEventType] = useState<string>();
  const [eventSource, setEventSource] = useState<string>();
  const [aggregateType, setAggregateType] = useState<string>();
  const [severity, setSeverity] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [keyword, setKeyword] = useState('');
  const [occurredFrom, setOccurredFrom] = useState<string>();
  const [occurredTo, setOccurredTo] = useState<string>();
  const [page, setPage] = useState(1);
  const filters = {
    eventType,
    eventSource,
    aggregateType,
    severity,
    status,
    keyword,
    occurredFrom,
    occurredTo,
    page,
    pageSize: DEFAULT_PAGE_SIZE,
  };
  const query = useQuery({
    queryKey: eventsQueryKey(tenantId, filters),
    queryFn: ({ signal }) => fetchEvents(filters, signal),
    enabled: tenantId != null,
  });

  const columns: ColumnsType<SystemEvent> = [
    {
      title: '发生时间',
      dataIndex: 'occurred_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
    { title: '事件类型', dataIndex: 'event_type', width: 220 },
    {
      title: '级别',
      dataIndex: 'severity',
      width: 90,
      render: (value: string) => (
        <Tag color={SEVERITY_COLOR[value] ?? 'default'}>{eventSeverityLabel(value)}</Tag>
      ),
    },
    { title: '来源', dataIndex: 'event_source', width: 90 },
    {
      title: '业务对象',
      key: 'aggregate',
      width: 180,
      render: (_, row) => `${row.aggregate_type}${row.aggregate_id ? `#${row.aggregate_id}` : ''}`,
    },
    { title: '标题', dataIndex: 'title', width: 240, render: (value: string) => <EllipsisCell value={value} /> },
    {
      title: '处理状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => EVENT_STATUS_LABEL[value] ?? value,
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/system/events/${row.event_id}`)}>
            详情
          </Button>
          {eventBusinessPath(row.aggregate_type, row.aggregate_id) ? (
            <Button
              type="link"
              onClick={() => navigate(eventBusinessPath(row.aggregate_type, row.aggregate_id)!)}
            >
              原单
            </Button>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <ListPageContainer>
      <PageHeader title={props.title ?? '事件中心'} description={props.description} />
      <ListToolbar>
        <Space wrap>
          <Input
            allowClear
            placeholder="标题 / 事件ID"
            value={keyword}
            onChange={(event) => {
              setKeyword(event.target.value);
              setPage(1);
            }}
            style={{ width: 180 }}
          />
          <Input
            allowClear
            placeholder="事件类型"
            value={eventType}
            onChange={(event) => {
              setEventType(event.target.value || undefined);
              setPage(1);
            }}
            style={{ width: 200 }}
          />
          <Select
            allowClear
            placeholder="来源"
            value={eventSource}
            style={{ width: 120 }}
            options={[
              { value: 'ERP', label: 'ERP' },
              { value: 'SYSTEM', label: 'SYSTEM' },
              { value: 'TASK', label: 'TASK' },
            ]}
            onChange={(value) => {
              setEventSource(value);
              setPage(1);
            }}
          />
          <Input
            allowClear
            placeholder="业务聚合"
            value={aggregateType}
            onChange={(event) => {
              setAggregateType(event.target.value || undefined);
              setPage(1);
            }}
            style={{ width: 160 }}
          />
          <Select
            allowClear
            placeholder="级别"
            value={severity}
            style={{ width: 120 }}
            options={Object.entries(EVENT_SEVERITY_LABEL).map(([value, label]) => ({ value, label }))}
            onChange={(value) => {
              setSeverity(value);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="处理状态"
            value={status}
            style={{ width: 120 }}
            options={Object.entries(EVENT_STATUS_LABEL).map(([value, label]) => ({ value, label }))}
            onChange={(value) => {
              setStatus(value);
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
          rowKey="event_id"
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
