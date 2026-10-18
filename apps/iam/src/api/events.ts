import type { ApiResponse, SystemEvent, SystemEventList } from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchEvents(
  params: {
    eventType?: string;
    eventSource?: string;
    aggregateType?: string;
    aggregateId?: number;
    severity?: string;
    status?: string;
    keyword?: string;
    occurredFrom?: string;
    occurredTo?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<SystemEventList>>('/api/v1/events', {
      params: {
        event_type: params.eventType || undefined,
        event_source: params.eventSource || undefined,
        aggregate_type: params.aggregateType || undefined,
        aggregate_id: params.aggregateId,
        severity: params.severity || undefined,
        status: params.status || undefined,
        keyword: params.keyword || undefined,
        occurred_from: params.occurredFrom,
        occurred_to: params.occurredTo,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchEvent(eventId: string, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<SystemEvent>>(`/api/v1/events/${eventId}`, { signal }),
  );
}
