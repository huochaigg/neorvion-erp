import { describe, expect, it } from 'vitest';
import {
  composeVisibleMessages,
  pendingUserMessage,
  seedConversationWithUser,
  turnHasTerminalAssistant,
  turnHasUser,
} from './chatMessages';
import type { Message } from '@/types';

function user(id: number, content: string): Message {
  return {
    id,
    role: 'user',
    content,
    status: 'COMPLETED',
    request_id: `u-${id}`,
    created_at: '',
    updated_at: '',
    tool_runs: [],
    evidences: [],
  };
}

function assistant(id: number, content: string, status = 'COMPLETED'): Message {
  return {
    id,
    role: 'assistant',
    content,
    status,
    request_id: `a-${id}`,
    created_at: '',
    updated_at: '',
    tool_runs: [],
    evidences: [],
  };
}

describe('composeVisibleMessages', () => {
  it('发送后立刻展示用户消息和助手占位，不必等会话详情返回', () => {
    const pending = pendingUserMessage('你好', 'req-1');
    const visible = composeVisibleMessages({
      messages: [],
      pendingUser: pending,
      pendingFromIndex: 0,
      showLiveAssistant: true,
      draft: '',
      tools: [],
      evidences: [],
      analysisStatus: '正在分析',
      agentRun: null,
    });
    expect(visible.map((item) => [item.role, item.content, item.status])).toEqual([
      ['user', '你好', 'COMPLETED'],
      ['assistant', '', 'RUNNING'],
    ]);
  });

  it('服务端已带回本轮用户消息时不再重复插入', () => {
    const pending = pendingUserMessage('你好', 'req-1');
    const visible = composeVisibleMessages({
      messages: [user(11, '你好'), assistant(12, '', 'RUNNING')],
      pendingUser: pending,
      pendingFromIndex: 0,
      showLiveAssistant: true,
      draft: '您好',
      tools: [],
      evidences: [],
      analysisStatus: '',
      agentRun: null,
    });
    expect(visible.filter((item) => item.role === 'user')).toHaveLength(1);
    expect(visible.at(-1)).toMatchObject({ role: 'assistant', content: '您好', status: 'RUNNING' });
  });

  it('相同内容的历史用户消息不会吞掉新的一轮', () => {
    const pending = pendingUserMessage('你好', 'req-2');
    expect(turnHasUser([user(1, '你好'), assistant(2, '在')], 2, pending)).toBe(false);
    const visible = composeVisibleMessages({
      messages: [user(1, '你好'), assistant(2, '在')],
      pendingUser: pending,
      pendingFromIndex: 2,
      showLiveAssistant: true,
      draft: '',
      tools: [],
      evidences: [],
      analysisStatus: '',
      agentRun: null,
    });
    expect(visible.map((item) => item.content)).toEqual(['你好', '在', '你好', '']);
  });

  it('终态助手到达后停止直播占位', () => {
    expect(turnHasTerminalAssistant([user(1, '你好'), assistant(2, '您好')], 0)).toBe(true);
    const visible = composeVisibleMessages({
      messages: [user(1, '你好'), assistant(2, '您好')],
      pendingUser: pendingUserMessage('你好', 'req-1'),
      pendingFromIndex: 0,
      showLiveAssistant: false,
      draft: '您好',
      tools: [],
      evidences: [],
      analysisStatus: '',
      agentRun: null,
    });
    expect(visible).toHaveLength(2);
    expect(visible[1]?.id).toBe(2);
  });
});

describe('seedConversationWithUser', () => {
  it('空缓存时写入本轮用户消息', () => {
    const pending = pendingUserMessage('你好', 'req-1');
    const seeded = seedConversationWithUser(undefined, 9, pending);
    expect(seeded.id).toBe(9);
    expect(seeded.messages).toEqual([pending]);
  });
});
