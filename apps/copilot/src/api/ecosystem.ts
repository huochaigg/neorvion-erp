import { api, unwrap } from '@/api/client';

export interface McpServer { id: number; server_key: string; display_name: string; endpoint: string; credential_reference?: string; credential_configured: boolean; enabled: boolean; approval_status: string; health_status: string; configuration_version: number }
export interface McpTool { id: number; server_id: number; tool_name: string; qualified_name: string; description: string; required_permissions: string[]; allowed_agents: string[]; risk_level: string; enabled: boolean; approval_status: string; schema_hash: string }
export interface Skill { id: number; skill_key: string; name: string; description: string; current_version: number; enabled: boolean; approval_status: string }
export interface SkillVersion { id: number; skill_id: number; version: number; instructions: string; input_schema: JsonSchema; output_schema: JsonSchema; allowed_agents: string[]; required_permissions: string[]; allowed_tools: string[]; required_evidence: boolean; risk_level: string; timeout_seconds: number; token_budget: number; source_format: 'JSON_TEMPLATE'|'SKILL_MD'; source_metadata: Record<string, unknown>; resources: Record<string, string>; content_hash: string; approval_status: string; created_by: number; created_at: string }
export interface SkillDetail extends Skill { versions: SkillVersion[] }
export interface JsonSchema { type: string; properties?: Record<string, JsonSchema>; required?: string[]; description?: string; format?: string; items?: JsonSchema; minLength?: number; maxLength?: number; minimum?: number; maximum?: number; minItems?: number; maxItems?: number }
export interface SkillRun { id: number; skill_id: number; skill_version: number; user_id: number; conversation_id?: number|null; message_id?: number|null; selection_method?: string|null; selection_snapshot?: Record<string, unknown>; plan_id?: number|null; plan_step_key?: string|null; idempotency_key: string; status: string; input_snapshot: Record<string, unknown>; output_snapshot: { result?: Record<string, unknown>; evidence?: Record<string, unknown>[]; tool_calls?: Record<string, unknown>[]; execution?: Record<string, unknown>; loaded_resources?: string[] }; safe_error: string | null; started_at: string | null; finished_at: string | null; created_at: string }
export interface SkillPlanStep { id:number;step_key:string;position:number;skill_id:number;skill_version_id:number;agent_name:string;depends_on:string[];status:string;input_snapshot:Record<string,unknown>;result_snapshot:Record<string,unknown>;safe_error?:string|null }
export interface SkillPlan { id:number;conversation_id:number;message_id:number;status:string;classification:Record<string,unknown>;selection_snapshot:Record<string,unknown>;budget_snapshot:Record<string,unknown>;steps:SkillPlanStep[];safe_error?:string|null }
export interface SkillVersionDiff { skill_id:number;from_version:number;to_version:number;changed_fields:string[];instructions_diff:string[] }
export interface SkillTemplateImportResult { skill_key: string; skill_id: number; version: number; status: 'IMPORTED' | 'UNCHANGED' | 'PROTECTED' }
export interface RunnableSkill { skill_id:number;version_id:number;skill_key:string;name:string;description:string;version:number;category:string;required_permissions:string[] }
export interface RunnableSkillCatalog { auto_available:boolean;default_mode:'AUTO'|'NONE';selector_profile:string;query_latency_ms:number;items:RunnableSkill[] }

export const listMcpServers = (signal?: AbortSignal) => unwrap<McpServer[]>(api.get('/api/v1/ecosystem/mcp/servers', { signal }));
export const createMcpServer = (payload: Record<string, unknown>) => unwrap<McpServer>(api.post('/api/v1/ecosystem/mcp/servers', payload));
export const probeMcpServer = (id: number) => unwrap<McpServer>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/probe`));
export const discoverMcpTools = (id: number) => unwrap<McpTool[]>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/discover`));
export const reviewMcpServer = (id: number, approved: boolean) => unwrap<McpServer>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/review`, { approved }));
export const setMcpServerEnabled = (id: number, approved: boolean) => unwrap<McpServer>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/enabled`, { approved }));
export const listMcpTools = (signal?: AbortSignal) => unwrap<McpTool[]>(api.get('/api/v1/ecosystem/mcp/tools', { signal }));
export const reviewMcpTool = (id: number, approved: boolean) => unwrap<McpTool>(api.post(`/api/v1/ecosystem/mcp/tools/${id}/review`, { approved, required_permissions: [], resource_requirements: {}, allowed_agents: [], timeout_seconds: 10 }));
export const listSkills = (signal?: AbortSignal) => unwrap<Skill[]>(api.get('/api/v1/ecosystem/skills', { signal }));
export const discoverRunnableSkills = (signal?: AbortSignal) => unwrap<RunnableSkillCatalog>(api.get('/api/v1/ecosystem/skills/catalog', { signal }));
export const createSkill = (payload: Record<string, unknown>) => unwrap<Skill>(api.post('/api/v1/ecosystem/skills', payload));
export const reviewSkill = (id: number, approved: boolean) => unwrap<Skill>(api.post(`/api/v1/ecosystem/skills/${id}/review`, { approved }));
export const getSkill = (id: number, signal?: AbortSignal) => unwrap<SkillDetail>(api.get(`/api/v1/ecosystem/skills/${id}`, { signal }));
export const createSkillVersion = (id: number, payload: Record<string, unknown>) => unwrap<SkillDetail>(api.post(`/api/v1/ecosystem/skills/${id}/versions`, payload));
export const rollbackSkill = (id: number, version: number) => unwrap<SkillDetail>(api.post(`/api/v1/ecosystem/skills/${id}/rollback`, { version }));
export const setSkillEnabled = (id: number, approved: boolean) => unwrap<SkillDetail>(api.post(`/api/v1/ecosystem/skills/${id}/enabled`, { approved }));
export const setSkillDeprecated = (id: number, approved: boolean) => unwrap<SkillDetail>(api.post(`/api/v1/ecosystem/skills/${id}/deprecated`, { approved }));
export const importSkillTemplates = (skillKeys?: string[]) => unwrap<SkillTemplateImportResult[]>(api.post('/api/v1/ecosystem/skills/templates/import', { skill_keys: skillKeys }));
export const importSkillPackage = (file: File) => {
  const form = new FormData();
  form.append('archive', file);
  return unwrap<SkillTemplateImportResult>(api.post('/api/v1/ecosystem/skills/packages/import', form));
};
export const runSkill = (id: number, payload: { input: Record<string, unknown>; idempotency_key: string; agent_name?: string }) => unwrap<SkillRun>(api.post(`/api/v1/ecosystem/skills/${id}/runs`, payload));
export const listSkillRuns = (id: number, signal?: AbortSignal) => unwrap<SkillRun[]>(api.get(`/api/v1/ecosystem/skills/${id}/runs`, { signal }));
export const getSkillRun = (skillId: number, runId: number, signal?: AbortSignal) => unwrap<SkillRun>(api.get(`/api/v1/ecosystem/skills/${skillId}/runs/${runId}`, { signal }));
export const getSkillPlan = (planId: number, signal?: AbortSignal) => unwrap<SkillPlan>(api.get(`/api/v1/ecosystem/skill-plans/${planId}`, { signal }));
export const diffSkillVersions = (skillId: number, fromVersion: number, toVersion: number, signal?: AbortSignal) => unwrap<SkillVersionDiff>(api.get(`/api/v1/ecosystem/skills/${skillId}/versions/diff`, { params: { from_version: fromVersion, to_version: toVersion }, signal }));
