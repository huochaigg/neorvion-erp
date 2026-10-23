import type { ApiResponse } from '@neorvion/shared';
import { api, unwrap } from './client';
import type { ActionProposal, ActionProposalList, CurrentIdentity, ProposalRevision } from '@/types';

export const listProposals = (signal?: AbortSignal, conversationId?: number) =>
  unwrap(api.get<ApiResponse<ActionProposalList>>('/api/v1/action-proposals', {
    signal,
    params: { page: 1, page_size: 100, conversation_id: conversationId },
  }));

export const getProposal = (id: number, signal?: AbortSignal) =>
  unwrap(api.get<ApiResponse<ActionProposal>>(`/api/v1/action-proposals/${id}`, { signal }));

export const updateProposal = (proposal: ActionProposal, payload: Record<string, unknown>) =>
  unwrap(api.patch<ApiResponse<ActionProposal>>(`/api/v1/action-proposals/${proposal.id}`, {
    expected_revision: proposal.current_revision,
    action: { action_type: proposal.action_type, payload },
  }));

export const validateProposal = (proposal: ActionProposal) =>
  unwrap(api.post<ApiResponse<ActionProposal>>(`/api/v1/action-proposals/${proposal.id}/validate`, {
    expected_revision: proposal.current_revision,
  }));

export const cancelProposal = (proposal: ActionProposal) =>
  unwrap(api.post<ApiResponse<ActionProposal>>(`/api/v1/action-proposals/${proposal.id}/cancel`, {
    expected_revision: proposal.current_revision,
  }));

export const listProposalRevisions = (id: number, signal?: AbortSignal) =>
  unwrap(api.get<ApiResponse<{items: ProposalRevision[]}>>(`/api/v1/action-proposals/${id}/revisions`, { signal }));

export const getCurrentIdentity = (signal?: AbortSignal) =>
  unwrap(api.get<ApiResponse<CurrentIdentity>>('/api/v1/me', { signal }));
