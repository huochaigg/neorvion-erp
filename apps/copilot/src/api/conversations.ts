import type { ApiResponse } from '@neorvion/shared';
import { api, unwrap } from './client';
import type { Conversation, ConversationDetail, ConversationList } from '@/types';

export const listConversations = (signal?: AbortSignal) =>
  unwrap(api.get<ApiResponse<ConversationList>>('/api/v1/conversations', { signal }));

export const getConversation = (id: number, signal?: AbortSignal) =>
  unwrap(
    api.request<ApiResponse<ConversationDetail>>({
      method: 'GET',
      url: `/api/v1/conversations/${id}`,
      signal,
    }),
  );

export const createConversation = (title = '新对话') =>
  unwrap(api.post<ApiResponse<Conversation>>('/api/v1/conversations', { title }));

export const renameConversation = (id: number, title: string) =>
  unwrap(api.patch<ApiResponse<Conversation>>(`/api/v1/conversations/${id}`, { title }));

export const deleteConversation = (id: number) => api.delete(`/api/v1/conversations/${id}`);
