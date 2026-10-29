import { api, unwrap } from '@/api/client';

export interface McpServer { id: number; server_key: string; display_name: string; endpoint: string; credential_reference?: string; credential_configured: boolean; enabled: boolean; approval_status: string; health_status: string; configuration_version: number }
export interface McpTool { id: number; server_id: number; tool_name: string; qualified_name: string; description: string; required_permissions: string[]; allowed_agents: string[]; risk_level: string; enabled: boolean; approval_status: string; schema_hash: string }
export interface Skill { id: number; skill_key: string; name: string; description: string; current_version: number; enabled: boolean; approval_status: string }

export const listMcpServers = (signal?: AbortSignal) => unwrap<McpServer[]>(api.get('/api/v1/ecosystem/mcp/servers', { signal }));
export const createMcpServer = (payload: Record<string, unknown>) => unwrap<McpServer>(api.post('/api/v1/ecosystem/mcp/servers', payload));
export const probeMcpServer = (id: number) => unwrap<McpServer>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/probe`));
export const discoverMcpTools = (id: number) => unwrap<McpTool[]>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/discover`));
export const reviewMcpServer = (id: number, approved: boolean) => unwrap<McpServer>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/review`, { approved }));
export const setMcpServerEnabled = (id: number, approved: boolean) => unwrap<McpServer>(api.post(`/api/v1/ecosystem/mcp/servers/${id}/enabled`, { approved }));
export const listMcpTools = (signal?: AbortSignal) => unwrap<McpTool[]>(api.get('/api/v1/ecosystem/mcp/tools', { signal }));
export const reviewMcpTool = (id: number, approved: boolean) => unwrap<McpTool>(api.post(`/api/v1/ecosystem/mcp/tools/${id}/review`, { approved, required_permissions: [], resource_requirements: {}, allowed_agents: [], timeout_seconds: 10 }));
export const listSkills = (signal?: AbortSignal) => unwrap<Skill[]>(api.get('/api/v1/ecosystem/skills', { signal }));
export const createSkill = (payload: Record<string, unknown>) => unwrap<Skill>(api.post('/api/v1/ecosystem/skills', payload));
export const reviewSkill = (id: number, approved: boolean) => unwrap<Skill>(api.post(`/api/v1/ecosystem/skills/${id}/review`, { approved }));
