import { ApiError } from '@neorvion/shared';
import { describe, expect, it, vi } from 'vitest';
import {
  canRetryMessage,
  classifySubscribeFailure,
  hasRunnableDetails,
  hasVisibleAgentTrace,
  isTerminalMessageStatus,
  listenWithReconnect,
  nextReconnectDelay,
  reconnectBudgetKey,
  rememberEventSeq,
  resetReconnectBudget,
  runStatusHint,
  runStatusLabel,
  SSE_MAX_RECONNECT_ATTEMPTS,
} from './runConnection';

describe('runConnection', () => {
  it('终态消息不再展示永久 Loading', () => {
    expect(isTerminalMessageStatus('INTERRUPTED')).toBe(true);
    expect(isTerminalMessageStatus('TIMED_OUT')).toBe(true);
    expect(isTerminalMessageStatus('RUNNING')).toBe(false);
  });

  it('按 sequence 去重，避免重放重复追加', () => {
    const seen = new Set<number>();
    expect(rememberEventSeq(seen, 1)).toBe(true);
    expect(rememberEventSeq(seen, 1)).toBe(false);
    expect(rememberEventSeq(seen, 2)).toBe(true);
  });

  it('重连延迟为 1s、2s、4s、8s、16s 并带抖动', () => {
    expect(nextReconnectDelay(1, () => 0.5)).toBe(1000);
    expect(nextReconnectDelay(2, () => 0.5)).toBe(2000);
    expect(nextReconnectDelay(5, () => 0.5)).toBe(16000);
    expect(nextReconnectDelay(8, () => 0.5)).toBe(16000);
  });

  it('调试断开时提示断点等待而不是失败', () => {
    expect(
      runStatusLabel({
        status: 'RUNNING',
        connection: 'DISCONNECTED',
        debugExecution: true,
      }),
    ).toContain('断点暂停');
  });

  it('自动重连失败后展示明确降级文案', () => {
    expect(
      runStatusLabel({
        status: 'RUNNING',
        connection: 'RECONNECT_FAILED',
      }),
    ).toContain('连接恢复失败');
    expect(
      runStatusLabel({
        status: 'RUNNING',
        connection: 'RECONNECTING',
        reconnectAttempt: 3,
        reconnectMaxAttempts: 5,
      }),
    ).toBe('正在重新连接（第 3 / 5 次）');
    expect(runStatusLabel({ status: 'INTERRUPTED' })).toBe('任务已中断');
  });

  it('已消费终态后停止自动重连', async () => {
    const subscribe = vi.fn(async () => undefined);
    const states: string[] = [];
    const abort = new AbortController();
    let terminal = false;
    await listenWithReconnect({
      subscribe: async () => {
        terminal = true;
        await subscribe();
      },
      signal: abort.signal,
      shouldRetry: () => !terminal,
      onState: (state) => states.push(state),
      delay: () => 1,
      sleep: async () => undefined,
    });
    expect(subscribe).toHaveBeenCalledTimes(1);
    expect(states[0]).toBe('CONNECTING');
  });

  it('HTTP 404 立即停止，不消耗剩余重连次数', async () => {
    const states: string[] = [];
    await listenWithReconnect({
      subscribe: async () => {
        throw new ApiError('消息不存在', { status: 404, code: 40481 });
      },
      signal: new AbortController().signal,
      shouldRetry: () => true,
      onState: (state) => states.push(state),
      delay: () => 1,
      sleep: async () => undefined,
      maxAttempts: 5,
    });
    expect(states.at(-1)).toBe('RECONNECT_FAILED');
    expect(states.filter((item) => item === 'CONNECTING')).toHaveLength(1);
    expect(classifySubscribeFailure(new ApiError('nope', { status: 404, code: 40481 }))).toBe('stop');
    expect(classifySubscribeFailure(new ApiError('down', { status: 503, code: 50381 }))).toBe('retry');
  });

  it('次数上限到达后进入 RECONNECT_FAILED，不因重复调用重置计数', async () => {
    const key = reconnectBudgetKey(27, 180);
    resetReconnectBudget(key);
    let clock = 0;
    const subscribe = vi.fn(async () => {
      throw new Error('network');
    });
    const run = () =>
      listenWithReconnect({
        budgetKey: key,
        subscribe,
        signal: new AbortController().signal,
        shouldRetry: () => true,
        onState: () => undefined,
        now: () => clock,
        delay: () => 1000,
        sleep: async (ms) => {
          clock += ms;
        },
        maxAttempts: 5,
        maxDurationMs: 60_000,
      });
    await run();
    expect(subscribe).toHaveBeenCalledTimes(5);
    subscribe.mockClear();
    await run();
    expect(subscribe).toHaveBeenCalledTimes(0);
    resetReconnectBudget(key);
    await run();
    expect(subscribe).toHaveBeenCalledTimes(5);
  });

  it('超过最大恢复时间后停止自动重连', async () => {
    let clock = 0;
    const subscribe = vi.fn(async () => {
      throw new Error('network');
    });
    await listenWithReconnect({
      subscribe,
      signal: new AbortController().signal,
      shouldRetry: () => true,
      onState: () => undefined,
      now: () => clock,
      delay: () => 10_000,
      sleep: async (ms) => {
        clock += ms;
      },
      maxAttempts: 50,
      maxDurationMs: 25_000,
    });
    expect(subscribe.mock.calls.length).toBeGreaterThan(0);
    expect(subscribe.mock.calls.length).toBeLessThan(50);
  });

  it('心跳不会被当成任务恢复成功', () => {
    expect(SSE_MAX_RECONNECT_ATTEMPTS).toBe(5);
    expect(
      runStatusLabel({
        status: 'RUNNING',
        connection: 'CONNECTED',
      }),
    ).toBe('正在理解问题');
  });

  it('统一映射内部状态，不把 PENDING 当作协作完成', () => {
    expect(runStatusHint({ status: 'INTERRUPTED', canRetry: true })).toContain('重新发送');
    expect(hasVisibleAgentTrace({ graph_type: 'PENDING', tasks: [] })).toBe(false);
    expect(hasVisibleAgentTrace({ graph_type: 'MULTI_AGENT', tasks: [{ id: 1 }] })).toBe(true);
    expect(
      hasRunnableDetails({
        agent_runs: [{ graph_type: 'PENDING', tasks: [] }],
        tool_runs: [],
        skill_runs: [],
        evidences: [],
      }),
    ).toBe(false);
    expect(canRetryMessage({ status: 'INTERRUPTED', can_retry: true, tool_runs: [] })).toBe(true);
    expect(canRetryMessage({ status: 'INTERRUPTED', tool_runs: [] })).toBe(true);
    expect(
      canRetryMessage({
        status: 'INTERRUPTED',
        can_retry: false,
        tool_runs: [{ status: 'SUCCEEDED' }],
      }),
    ).toBe(false);
  });
});
