import type { AgentRun, ConnectionState, ConversationDetail, Evidence, IntentStatus, Message, SkillRunSummary, ToolRun } from '@/types';

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
    skill_runs: [],
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
  skillRuns?: SkillRunSummary[];
  intentStatus?: IntentStatus | null;
  connectionState?: ConnectionState | null;
  connectionAttempt?: number;
  connectionMaxAttempts?: number;
}): Message[] {
  const hasUser = turnHasUser(input.messages, input.pendingFromIndex, input.pendingUser);
  const list =
    hasUser || input.pendingUser == null ? [...input.messages] : [...input.messages, input.pendingUser];
  if (!input.showLiveAssistant) {
    return list.map((item) =>
      item.role === 'assistant' && item.status === 'RUNNING'
        ? {
            ...item,
            connection_state: input.connectionState ?? item.connection_state,
            connection_attempt: input.connectionAttempt ?? item.connection_attempt,
            connection_max_attempts: input.connectionMaxAttempts ?? item.connection_max_attempts,
          }
        : item,
    );
  }

  const last = list[list.length - 1];
  const liveId = last?.role === 'assistant' && last.id > 0 ? last.id : -1;
  const streaming: Message = {
    id: liveId,
    role: 'assistant',
    content: input.draft || (liveId > 0 ? last.content : ''),
    status: last?.status === 'RUNNING' || liveId < 0 ? 'RUNNING' : (last?.status ?? 'RUNNING'),
    request_id: last?.request_id || input.pendingUser?.request_id || '',
    created_at: last?.created_at ?? '',
    updated_at: last?.updated_at ?? '',
    tool_runs: input.tools.length ? input.tools : last?.tool_runs ?? [],
    evidences: input.evidences.length ? input.evidences : last?.evidences ?? [],
    analysis_status: input.analysisStatus,
    agent_runs: input.agentRun ? [input.agentRun] : last?.agent_runs ?? [],
    skill_runs: input.skillRuns?.length ? input.skillRuns : last?.skill_runs ?? [],
    intent_status: input.intentStatus ?? last?.intent_status ?? null,
    last_event_seq: last?.last_event_seq,
    live: last?.live,
    interrupt_reason: last?.interrupt_reason,
    can_retry: last?.can_retry,
    retry_denied_reason: last?.retry_denied_reason,
    can_reconnect: last?.can_reconnect ?? last?.status === 'RUNNING',
    can_cancel: last?.can_cancel ?? last?.status === 'RUNNING',
    debug_execution: last?.debug_execution,
    connection_state: input.connectionState ?? undefined,
    connection_attempt: input.connectionAttempt,
    connection_max_attempts: input.connectionMaxAttempts,
  };
  if (last?.role === 'assistant' && (last.id < 0 || last.status === 'RUNNING')) {
    return [...list.slice(0, -1), streaming];
  }
  return [...list, streaming];
}

export function visibleMessageKey(message: Message, index: number) {
  if (message.id > 0) return `msg-${message.id}`;
  return `live-${message.role}-${message.request_id || index}-${message.id}`;
}
