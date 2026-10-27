import { api, unwrap } from '@/api/client';

export interface AIProvider {
  id: number;
  code: string;
  display_name: string;
  base_url: string;
  secret_env_name: string;
  secret_configured: boolean;
  status: 'ACTIVE' | 'DISABLED';
  data_region: string;
  last_probe_status: string;
  last_probe_at?: string;
}

export interface AIModel {
  id: number;
  provider_id: number;
  model_name: string;
  purposes: string[];
  enabled: boolean;
  supports_tools: boolean;
  context_window: number;
  max_output_tokens: number;
}

export interface GovernancePolicy {
  id: number;
  allowed_provider_codes: string[];
  allowed_model_names: string[];
  allowed_agents: string[];
  allowed_tools: string[];
  multi_agent_enabled: boolean;
  insight_analysis_enabled: boolean;
  live_evaluation_enabled: boolean;
  max_context_tokens: number;
  trace_retention_days: number;
  conversation_retention_days: number;
}

export interface TenantQuota {
  id: number;
  requests_per_minute: number;
  requests_per_day: number;
  monthly_token_limit: number;
  monthly_budget?: number;
  currency: string;
  max_concurrent_agents: number;
  max_concurrent_evaluations: number;
  insight_monthly_token_limit: number;
  max_tool_calls_per_request: number;
  max_execution_seconds: number;
  warning_threshold_percent: number;
  hard_limit: boolean;
}

export const listProviders = (signal?: AbortSignal) =>
  unwrap<AIProvider[]>(api.get('/api/v1/governance/providers', { signal }));
export const probeProvider = (id: number) =>
  unwrap<AIProvider>(api.post(`/api/v1/governance/providers/${id}/probe`));
export const createProvider = (payload: Omit<AIProvider, 'id' | 'secret_configured' | 'status' | 'last_probe_status'>) =>
  unwrap<AIProvider>(api.post('/api/v1/governance/providers', payload));
export const listModels = (signal?: AbortSignal) =>
  unwrap<AIModel[]>(api.get('/api/v1/governance/models', { signal }));
export const getGovernancePolicy = (signal?: AbortSignal) =>
  unwrap<GovernancePolicy>(api.get('/api/v1/governance/policy', { signal }));
export const updateGovernancePolicy = (payload: Omit<GovernancePolicy, 'id'>) =>
  unwrap<GovernancePolicy>(api.put('/api/v1/governance/policy', payload));
export const getTenantQuota = (signal?: AbortSignal) =>
  unwrap<TenantQuota>(api.get('/api/v1/governance/quota', { signal }));
export const getAIUsage = (signal?: AbortSignal) =>
  unwrap<Record<string, unknown>>(api.get('/api/v1/governance/usage', { signal }));
export const getAIOperations = (signal?: AbortSignal) =>
  unwrap<Record<string, number | string | null>>(api.get('/api/v1/governance/operations', { signal }));
export const listGovernanceAudits = (signal?: AbortSignal) =>
  unwrap<Array<Record<string, unknown>>>(api.get('/api/v1/governance/audits', { signal }));
export const previewRetention = () =>
  unwrap<Record<string, unknown>>(api.post('/api/v1/governance/retention/preview', { dry_run: true }));
