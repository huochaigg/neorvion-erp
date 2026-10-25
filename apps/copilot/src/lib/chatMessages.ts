import type { AgentRun, ConversationDetail, Evidence, Message, ToolRun } from '@/types';

export function pendingUserMessage(content: string, requestId: string): Message {
  const now = new Date().toISOString();
  return {
    id: -2,
    role: 'user',
    content,
    status: 'COMPLETED',
    request_id: requestId,
    created_at: now,
    updated_at: now,
    tool_runs: [],
    evidences: [],
  };
}

export function turnHasUser(messages: Message[], fromIndex: number, pending: Message | null) {
  if (pending == null) return true;
  return messages
    .slice(Math.max(0, fromIndex))
    .some((item) => item.role === 'user' && item.content === pending.content);
}

export function turnHasTerminalAssistant(messages: Message[], fromIndex: number) {
  return messages
    .slice(Math.max(0, fromIndex))
    .some((item) => item.role === 'assistant' && item.status !== 'RUNNING');
}

export function seedConversationWithUser(
  detail: ConversationDetail | undefined,
  conversationId: number,
  user: Message,
  title = '新对话',
): ConversationDetail {
  if (!detail) {
    return {
      id: conversationId,
      title,
      status: 'ACTIVE',
      created_at: user.created_at,
      updated_at: user.updated_at,
      messages: [user],
    };
  }
  const last = detail.messages.at(-1);
  if (last?.role === 'user' && (last.id === user.id || last.request_id === user.request_id)) {
    return detail;
  }
  return { ...detail, messages: [...detail.messages, user] };
}

export function composeVisibleMessages(input: {
  messages: Message[];
  pendingUser: Message | null;
  pendingFromIndex: number;
  showLiveAssistant: boolean;
  draft: string;
  tools: ToolRun[];
  evidences: Evidence[];
  analysisStatus: string;
  agentRun: AgentRun | null;
}): Message[] {
  const hasUser = turnHasUser(input.messages, input.pendingFromIndex, input.pendingUser);
  const list =
    hasUser || input.pendingUser == null ? [...input.messages] : [...input.messages, input.pendingUser];
  if (!input.showLiveAssistant) return list;

  const streaming: Message = {
    id: -1,
    role: 'assistant',
    content: input.draft,
    status: 'RUNNING',
    request_id: input.pendingUser?.request_id ?? '',
    created_at: '',
    updated_at: '',
    tool_runs: input.tools,
    evidences: input.evidences,
    analysis_status: input.analysisStatus,
    agent_runs: input.agentRun ? [input.agentRun] : [],
  };
  const last = list[list.length - 1];
  if (last?.role === 'assistant' && (last.id < 0 || last.status === 'RUNNING')) {
    return [...list.slice(0, -1), streaming];
  }
  return [...list, streaming];
}
