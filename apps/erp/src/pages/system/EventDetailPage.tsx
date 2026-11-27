import {
  EVENT_STATUS_LABEL,
  eventBusinessPath,
  eventQueryKey,
  eventSeverityLabel,
} from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Button, Descriptions, Space, Tag } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { fetchEvent } from '@/api/events';
import { FormPageContainer } from '@/components/PageContainer';
import { PageHeader } from '@/components/PageHeader';
import { formatDateTime } from '@/lib/datetime';
import type { PageProps } from '@/router/types';
import { useErpTenantStore } from '@/stores/tenant-runtime';

export function EventDetailPage(_props: PageProps) {
  const { eventId = '' } = useParams();
  const navigate = useNavigate();
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  const query = useQuery({
    queryKey: eventQueryKey(tenantId, eventId),
    queryFn: ({ signal }) => fetchEvent(eventId, signal),
    enabled: tenantId != null && Boolean(eventId),
  });
  const event = query.data;
  const businessPath = event ? eventBusinessPath(event.aggregate_type, event.aggregate_id) : null;

  return (
    <FormPageContainer>
      <PageHeader
        title="事件详情"
        extra={
          <Space>
            {businessPath ? (
              <Button onClick={() => navigate(businessPath)}>查看原业务</Button>
            ) : null}
            <Button onClick={() => navigate('/system/events')}>返回列表</Button>
          </Space>
        }
      />
      {event ? (
        <>
          <Descriptions bordered size="small" column={2} className="mb-4">
            <Descriptions.Item label="事件 ID">{event.event_id}</Descriptions.Item>
            <Descriptions.Item label="类型">{event.event_type}</Descriptions.Item>
            <Descriptions.Item label="来源">{event.event_source}</Descriptions.Item>
            <Descriptions.Item label="级别">
              <Tag>{eventSeverityLabel(event.severity)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="业务聚合">
              {event.aggregate_type}
              {event.aggregate_id != null ? ` #${event.aggregate_id}` : ''}
            </Descriptions.Item>
            <Descriptions.Item label="关联对象">
              {event.reference_type
                ? `${event.reference_type}${event.reference_id != null ? ` #${event.reference_id}` : ''}`
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="发生时间">{formatDateTime(event.occurred_at)}</Descriptions.Item>
            <Descriptions.Item label="处理状态">
              {EVENT_STATUS_LABEL[event.status] ?? event.status}
            </Descriptions.Item>
            <Descriptions.Item label="标题" span={2}>
              {event.title}
            </Descriptions.Item>
            <Descriptions.Item label="说明" span={2}>
              {event.message || '-'}
            </Descriptions.Item>
          </Descriptions>
          <h3 className="mb-2 text-sm font-medium">Payload</h3>
          <pre className="mb-4 overflow-auto rounded bg-neutral-50 p-3 text-xs">
            {JSON.stringify(event.payload ?? {}, null, 2)}
          </pre>
          <h3 className="mb-2 text-sm font-medium">Metadata</h3>
          <pre className="overflow-auto rounded bg-neutral-50 p-3 text-xs">
            {JSON.stringify(event.metadata ?? {}, null, 2)}
          </pre>
        </>
      ) : null}
    </FormPageContainer>
  );
}
