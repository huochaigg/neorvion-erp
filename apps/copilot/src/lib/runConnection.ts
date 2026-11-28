import { ApiError } from '@neorvion/shared';

export type ConnectionState =
  | 'CONNECTING'
  | 'CONNECTED'
  | 'RECONNECTING'
  | 'RECONNECT_FAILED'
  | 'DISCONNECTED'
  | 'WAITING_TOO_LONG';

export const SSE_MAX_RECONNECT_ATTEMPTS = 5;
export const SSE_MAX_RECONNECT_DURATION_MS = 60_000;
const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 16_000];

export const TERMINAL_MESSAGE_STATUSES = [
  'COMPLETED',
  'FAILED',
  'CANCELLED',
  'INTERRUPTED',
  'TIMED_OUT',
] as const;

type ReconnectBudget = { attempts: number; startedAt: number };

const reconnectBudgets = new Map<string, ReconnectBudget>();

export function isTerminalMessageStatus(status: string | undefined) {
  return TERMINAL_MESSAGE_STATUSES.includes(status as (typeof TERMINAL_MESSAGE_STATUSES)[number]);
}

export function isTerminalSseEvent(event: string) {
  return event === 'done' || event === 'error';
}

export function isHeartbeatEvent(event: string) {
  return event === 'ping' || event === 'heartbeat';
}

export function nextReconnectDelay(attempt: number, random = Math.random) {
  const index = Math.min(Math.max(attempt, 1), RECONNECT_DELAYS_MS.length) - 1;
  const base = RECONNECT_DELAYS_MS[index] ?? 16_000;
  return Math.round(base * (0.85 + random() * 0.3));
}

/** 按 sequence 去重；心跳事件不占用业务游标。 */
export function rememberEventSeq(seen: Set<number>, seq: unknown) {
  const value = Number(seq);
  if (!Number.isFinite(value) || value <= 0) return true;
  if (seen.has(value)) return false;
  seen.add(value);
  return true;
}

export function reconnectBudgetKey(conversationId: number, messageId: number) {
  return `${conversationId}:${messageId}`;
}

export function resetReconnectBudget(key: string) {
  reconnectBudgets.delete(key);
}

export function peekReconnectBudget(key: string) {
  return reconnectBudgets.get(key);
}

export function classifySubscribeFailure(error: unknown): 'retry' | 'stop' {
  if (error instanceof ApiError) {
    if (error.status === 408 || error.status === 429) return 'retry';
    if (error.status >= 500) return 'retry';
    if (error.status >= 400 && error.status < 500) return 'stop';
  }
  return 'retry';
}

const MESSAGE_STATUS_LABELS: Record<string, string> = {
  INTERRUPTED: '任务已中断',
  TIMED_OUT: '任务执行超时',
  FAILED: '任务执行失败',
  CANCELLED: '已停止生成',
};

const RUN_STATUS_LABELS: Record<string, string> = {
  RUNNING: '进行中',
  SUCCEEDED: '已完成',
  FAILED: '失败',
  CANCELLED: '已停止',
  INTERRUPTED: '已中断',
  TIMED_OUT: '已超时',
  DEGRADED: '部分任务未完成',
};

const TASK_STATUS_LABELS: Record<string, string> = {
  RUNNING: '进行中',
  SUCCEEDED: '已完成',
  FAILED: '失败',
  CANCELLED: '已停止',
  PENDING: '等待中',
};

export function runStatusLabel(input: {
  status: string;
  connection?: ConnectionState | null;
  debugExecution?: boolean;
  interruptReason?: string | null;
  cancelRequested?: boolean;
  reconnectAttempt?: number;
  reconnectMaxAttempts?: number;
  graphType?: string | null;
}) {
  if (input.cancelRequested || input.interruptReason === 'cancel_requested') return '正在取消任务';
  if (MESSAGE_STATUS_LABELS[input.status]) return MESSAGE_STATUS_LABELS[input.status];
  if (input.status === 'COMPLETED') return '';
  if (input.status !== 'RUNNING') return '';
  if (input.connection === 'RECONNECT_FAILED' && input.debugExecution) {
    return '服务端可能正在断点暂停，等待服务端恢复。';
  }
  if (input.connection === 'RECONNECT_FAILED') {
    return '连接恢复失败，暂时无法获取任务状态。';
  }
  if (input.debugExecution && (input.connection === 'DISCONNECTED' || input.connection === 'RECONNECTING' || input.connection === 'WAITING_TOO_LONG')) {
    return '服务端可能正在断点暂停，等待服务端恢复。';
  }
  if (input.connection === 'RECONNECTING') {
    const attempt = input.reconnectAttempt ?? 1;
    const max = input.reconnectMaxAttempts ?? SSE_MAX_RECONNECT_ATTEMPTS;
    return `正在重新连接（第 ${attempt} / ${max} 次）`;
  }
  if (input.connection === 'CONNECTING') return '正在连接服务端';
  if (input.connection === 'DISCONNECTED') return '连接已断开，任务仍可能在后台执行';
  if (input.connection === 'WAITING_TOO_LONG') return '任务耗时较长，仍在等待服务端进度';
  if (input.graphType === 'PENDING' || !input.graphType) return '正在理解问题';
  return '正在处理';
}

export function runStatusHint(input: { status: string; canRetry?: boolean; retryDeniedReason?: string | null }) {
  if (input.retryDeniedReason) return input.retryDeniedReason;
  if (input.status === 'INTERRUPTED' && input.canRetry) return '本次任务未能完成，请重新发送消息。';
  if (input.status === 'FAILED' && input.canRetry) return '任务未能完成，可以重新发送原问题。';
  if (input.status === 'TIMED_OUT' && input.canRetry) return '可以重新发送原问题再试一次。';
  if (input.status === 'CANCELLED' && input.canRetry) return '可以重新生成回答。';
  return '';
}

export function agentGraphLabel(graphType: string | undefined) {
  if (graphType === 'MULTI_AGENT') return '多 Agent 协作';
  if (graphType === 'SINGLE_AGENT') return '单一 Agent';
  return '';
}

export function agentRunStatusLabel(status: string) {
  return RUN_STATUS_LABELS[status] || '';
}

export function agentTaskStatusLabel(status: string) {
  return TASK_STATUS_LABELS[status] || '';
}

export function hasVisibleAgentTrace(run: { graph_type?: string; tasks?: unknown[] }) {
  const tasks = run.tasks?.length ?? 0;
  if (tasks > 0) return true;
  return run.graph_type === 'SINGLE_AGENT' || run.graph_type === 'MULTI_AGENT';
}

export function hasRunnableDetails(message: {
  intent_status?: unknown;
  skill_runs?: unknown[];
  agent_runs?: Array<{ graph_type?: string; tasks?: unknown[] }>;
  tool_runs?: unknown[];
  evidences?: unknown[];
}) {
  if (message.intent_status) return true;
  if ((message.skill_runs?.length ?? 0) > 0) return true;
  if ((message.tool_runs?.length ?? 0) > 0) return true;
  if ((message.evidences?.length ?? 0) > 0) return true;
  return (message.agent_runs ?? []).some(hasVisibleAgentTrace);
}

export function canRetryMessage(message: {
  status: string;
  can_retry?: boolean;
  tool_runs?: Array<{ status: string }>;
}) {
  if (message.can_retry === true) return true;
  if (message.can_retry === false) return false;
  if (!['FAILED', 'INTERRUPTED', 'TIMED_OUT', 'CANCELLED'].includes(message.status)) return false;
  return !(message.tool_runs ?? []).some((run) => run.status === 'SUCCEEDED');
}

export async function listenWithReconnect(options: {
  subscribe: (signal: AbortSignal) => Promise<void>;
  signal: AbortSignal;
  shouldRetry: () => boolean;
  onState: (state: ConnectionState) => void;
  budgetKey?: string;
  maxAttempts?: number;
  maxDurationMs?: number;
  now?: () => number;
  delay?: (attempt: number) => number;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  onAttempt?: (attempt: number, max: number) => void;
  classifyError?: (error: unknown) => 'retry' | 'stop';
}) {
  const delay = options.delay ?? ((attempt: number) => nextReconnectDelay(attempt));
  const sleep = options.sleep ?? sleepAbortable;
  const now = options.now ?? Date.now;
  const maxAttempts = options.maxAttempts ?? SSE_MAX_RECONNECT_ATTEMPTS;
  const maxDurationMs = options.maxDurationMs ?? SSE_MAX_RECONNECT_DURATION_MS;
  const classify = options.classifyError ?? classifySubscribeFailure;
  const budget = options.budgetKey
    ? (reconnectBudgets.get(options.budgetKey) ?? { attempts: 0, startedAt: now() })
    : { attempts: 0, startedAt: now() };
  if (options.budgetKey) reconnectBudgets.set(options.budgetKey, budget);

  const exhausted = () =>
    budget.attempts >= maxAttempts || now() - budget.startedAt >= maxDurationMs;

  while (!options.signal.aborted && options.shouldRetry()) {
    if (exhausted()) {
      options.onState('RECONNECT_FAILED');
      return;
    }
    const reconnecting = budget.attempts > 0;
    options.onState(reconnecting ? 'RECONNECTING' : 'CONNECTING');
    if (reconnecting) options.onAttempt?.(budget.attempts, maxAttempts);
    try {
      await options.subscribe(options.signal);
      if (options.signal.aborted || !options.shouldRetry()) return;
    } catch (error) {
      if (options.signal.aborted || !options.shouldRetry()) return;
      if (classify(error) === 'stop') {
        options.onState('RECONNECT_FAILED');
        return;
      }
    }
    budget.attempts += 1;
    if (exhausted() || options.signal.aborted || !options.shouldRetry()) {
      if (!options.signal.aborted && options.shouldRetry()) options.onState('RECONNECT_FAILED');
      return;
    }
    options.onState('RECONNECTING');
    options.onAttempt?.(budget.attempts, maxAttempts);
    await sleep(delay(budget.attempts), options.signal);
  }
  if (!options.signal.aborted && options.shouldRetry()) options.onState('RECONNECT_FAILED');
  else if (!options.signal.aborted) options.onState('DISCONNECTED');
}

export function sleepAbortable(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      signal.removeEventListener('abort', onAbort);
      resolve();
    };
    signal.addEventListener('abort', onAbort, { once: true });
    void reject;
  });
}
