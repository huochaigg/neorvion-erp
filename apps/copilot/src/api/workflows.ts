import type { ApiResponse } from '@neorvion/shared';
import { api, unwrap } from './client';
import type { ModelStatus, Workflow, WorkflowDetail, WorkflowList, WorkflowType } from '@/types';

export const modelStatus=(signal?:AbortSignal)=>unwrap(api.get<ApiResponse<ModelStatus>>('/api/v1/model-status',{signal}));
export const listWorkflows=(signal?:AbortSignal)=>unwrap(api.get<ApiResponse<WorkflowList>>('/api/v1/workflows',{signal}));
export const getWorkflow=(id:number,signal?:AbortSignal)=>unwrap(api.get<ApiResponse<WorkflowDetail>>(`/api/v1/workflows/${id}`,{signal}));
export const createWorkflow=(workflow_type:WorkflowType,input:Record<string,unknown>,conversation_id?:number)=>unwrap(api.post<ApiResponse<Workflow>>('/api/v1/workflows',{workflow_type,input,conversation_id,idempotency_key:crypto.randomUUID()}));
export const resumeWorkflow=(id:number,input:Record<string,unknown>)=>unwrap(api.post<ApiResponse<Workflow>>(`/api/v1/workflows/${id}/resume`,{input}));
export const retryWorkflow=(id:number)=>unwrap(api.post<ApiResponse<Workflow>>(`/api/v1/workflows/${id}/retry`));
export const cancelWorkflow=(id:number)=>unwrap(api.post<ApiResponse<Workflow>>(`/api/v1/workflows/${id}/cancel`));
