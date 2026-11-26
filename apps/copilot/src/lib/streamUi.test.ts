import { describe, expect, it, vi } from 'vitest';
import { createStreamFrameQueue, shouldApplyStreamEvent } from './streamUi';
import type { StreamEvent } from '@/types';

function message(delta: string): StreamEvent {
  return { event: 'message', data: { delta } };
}

describe('shouldApplyStreamEvent', () => {
  it('忽略已切换的旧 run', () => {
    expect(
      shouldApplyStreamEvent({
        runId: 'a',
        activeRunId: 'b',
        pendingConversationId: 1,
        selectedConversationId: 1,
      }),
    ).toBe(false);
  });

  it('忽略正在生成的旧会话事件，避免污染当前会话 UI', () => {
    expect(
      shouldApplyStreamEvent({
        runId: 'a',
        activeRunId: 'a',
        pendingConversationId: 1,
        selectedConversationId: 2,
      }),
    ).toBe(false);
  });

  it('当前会话的活跃 run 可以应用', () => {
    expect(
      shouldApplyStreamEvent({
        runId: 'a',
        activeRunId: 'a',
        pendingConversationId: 3,
        selectedConversationId: 3,
      }),
    ).toBe(true);
  });
});

describe('createStreamFrameQueue', () => {
  it('同一帧内的 token 合并为一次回调，且保持与控制事件的先后顺序', () => {
    const received: StreamEvent[] = [];
    const frames: Array<() => void> = [];
    const queue = createStreamFrameQueue({
      onEvent: (event) => received.push(event),
      schedule: (cb) => {
        frames.push(cb);
        return frames.length;
      },
      cancel: vi.fn(),
    });

    queue.push(message('你'));
    queue.push(message('好'));
    expect(received).toEqual([]);
    expect(queue.pending).toBe(1);

    queue.push({ event: 'tool_start', data: { name: 'get_inventory' } });
    expect(received).toEqual([
      { event: 'message', data: { delta: '你好' } },
      { event: 'tool_start', data: { name: 'get_inventory' } },
    ]);

    queue.push(message('库存'));
    queue.flush();
    expect(received.at(-1)).toEqual({ event: 'message', data: { delta: '库存' } });
  });

  it('close 后丢弃未刷新的 token，避免取消生成后继续更新 UI', () => {
    const onEvent = vi.fn();
    const frames: Array<() => void> = [];
    const queue = createStreamFrameQueue({
      onEvent,
      schedule: (cb) => {
        frames.push(cb);
        return frames.length;
      },
      cancel: vi.fn(),
    });
    queue.push(message('残留'));
    queue.close();
    frames[0]?.();
    expect(onEvent).not.toHaveBeenCalled();
    expect(queue.push(message('之后'))).toBe(false);
  });
});
