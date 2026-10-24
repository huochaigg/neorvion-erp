import type { ApiResponse } from '@neorvion/shared';
import { api, unwrap } from './client';
import type { ActionApprovalList, ActionAuditEvent, ActionExecution, ActionExecutionList, ActionProposal, ConfirmationTicket } from '@/types';

export const createConfirmation = (proposal: ActionProposal) => unwrap(api.post<ApiResponse<ConfirmationTicket>>(
  `/api/v1/action-proposals/${proposal.id}/confirmations`,
  { expected_revision: proposal.current_revision, client_request_id: crypto.randomUUID() },
));
export const confirmExecution = (ticket: ConfirmationTicket) => unwrap(api.post<ApiResponse<ActionExecution>>(
  `/api/v1/action-executions/${ticket.execution_id}/confirm`,
  { expected_revision: ticket.proposal_revision, confirmation_nonce: ticket.confirmation_nonce },
));
export const executeApproved = (value: ActionExecution) => unwrap(api.post<ApiResponse<ActionExecution>>(
  `/api/v1/action-executions/${value.id}/execute`, { expected_revision: value.proposal_revision },
));
export const reconcileExecution = (id: number) => unwrap(api.post<ApiResponse<ActionExecution>>(`/api/v1/action-executions/${id}/reconcile`));
export const getExecution = (id: number, signal?: AbortSignal) => unwrap(api.get<ApiResponse<ActionExecution>>(`/api/v1/action-executions/${id}`, { signal }));
export const listExecutions = (signal?: AbortSignal) => unwrap(api.get<ApiResponse<ActionExecutionList>>('/api/v1/action-executions', { signal }));
export const listApprovals = (signal?: AbortSignal) => unwrap(api.get<ApiResponse<ActionApprovalList>>('/api/v1/action-approvals', { signal }));
export const decideApproval = (id: number, approve: boolean, decisionReason?: string) => unwrap(api.post<ApiResponse<ActionExecution>>(
  `/api/v1/action-approvals/${id}/${approve ? 'approve' : 'reject'}`, { decision_reason: decisionReason || null },
));
export const listExecutionAudit = (id: number, signal?: AbortSignal) => unwrap(api.get<ApiResponse<{items:ActionAuditEvent[]}>>(`/api/v1/action-executions/${id}/audit`, { signal }));
