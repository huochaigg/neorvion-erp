import { api, unwrap } from '@/api/client';

export interface InsightRule { id: number; name: string; detector_type: string; detector_version: string; config: Record<string, unknown>; interval_minutes: number; enabled: boolean; next_run_at: string | null }
export interface BusinessInsight { id: number; rule_id: number; detector_type: string; resource_type: string; resource_id: string; severity: string; status: string; detected_at: string; last_seen_at: string; evidence_summary: Record<string, unknown>; analysis_status: string; ai_summary: string | null }
export interface InsightRun { id: number; rule_id: number; status: string; detected_count: number; duplicate_count: number; safe_error: string | null; created_at: string }
export interface InsightNotification { id: number; insight_id: number; title: string; safe_body: string; severity: string; read_at: string | null; created_at: string }
export interface Paged<T> { items: T[]; total: number; page: number; page_size: number }

export const listInsightRules = (signal?: AbortSignal) => unwrap<Paged<InsightRule>>(api.get('/api/v1/insight-rules', { signal }));
export const createInsightRule = (value: Record<string, unknown>) => unwrap<InsightRule>(api.post('/api/v1/insight-rules', value));
export const patchInsightRule = (id: number, value: Record<string, unknown>) => unwrap<InsightRule>(api.patch(`/api/v1/insight-rules/${id}`, value));
export const runInsightRule = (id: number) => unwrap<InsightRun>(api.post(`/api/v1/insight-rules/${id}/run`));
export const getInsightDashboard = (signal?: AbortSignal) => unwrap<{ open_total: number; severity: Record<string, number> }>(api.get('/api/v1/insights/dashboard', { signal }));
export const listInsights = (signal?: AbortSignal) => unwrap<Paged<BusinessInsight>>(api.get('/api/v1/insights', { signal }));
export const listInsightRuns = (signal?: AbortSignal) => unwrap<Paged<InsightRun>>(api.get('/api/v1/insight-runs', { signal }));
export const listInsightNotifications = (signal?: AbortSignal) => unwrap<Paged<InsightNotification>>(api.get('/api/v1/insight-notifications', { signal }));
export const acknowledgeInsight = (id: number) => unwrap<BusinessInsight>(api.post(`/api/v1/insights/${id}/acknowledge`));
export const closeInsight = (id: number) => unwrap<BusinessInsight>(api.post(`/api/v1/insights/${id}/close`));
export const readInsightNotification = (id: number) => unwrap<InsightNotification>(api.post(`/api/v1/insight-notifications/${id}/read`));
export const analyzeInsight = (id: number) => unwrap<BusinessInsight>(api.post(`/api/v1/insights/${id}/analyze`));
export const insightToChat = (id: number) => unwrap<{ conversation_id: number; initial_message: string }>(api.post(`/api/v1/insights/${id}/chat`));
export const insightToWorkflow = (id: number) => unwrap<{ workflow_id: number; workflow_type: string; status: string }>(api.post(`/api/v1/insights/${id}/workflow`));
