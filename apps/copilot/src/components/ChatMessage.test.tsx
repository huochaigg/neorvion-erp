import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ChatMessage } from './ChatMessage';
import type { Message } from '@/types';

function interrupted(): Message {
  return {
    id: 180,
    role: 'assistant',
    content: '',
    status: 'INTERRUPTED',
    request_id: '55ceae2d957a4e3c80002cd7deb8f6e4',
    created_at: '',
    updated_at: '',
    tool_runs: [],
    evidences: [],
    agent_runs: [{ id: 53, graph_type: 'PENDING', status: 'INTERRUPTED', route_reason: null, total_duration_ms: null, tasks: [] }],
    can_retry: true,
  };
}

describe('ChatMessage', () => {
  it('历史 PENDING 中断消息只展示用户可读状态和重新发送', () => {
    const html = renderToStaticMarkup(
      <ChatMessage message={interrupted()} onRetry={() => undefined} onViewRun={() => undefined} />,
    );
    expect(html).toContain('任务已中断');
    expect(html).toContain('本次任务未能完成，请重新发送消息。');
    expect(html).toContain('重新发送');
    expect(html).not.toContain('Agent 协作');
    expect(html).not.toContain('PENDING');
    expect(html).not.toContain('INTERRUPTED');
    expect(html).not.toContain('查看运行详情');
  });

  it('有真实 Agent Task 时才提供查看运行详情', () => {
    const message: Message = {
      ...interrupted(),
      agent_runs: [{
        id: 9,
        graph_type: 'SINGLE_AGENT',
        status: 'FAILED',
        route_reason: null,
        total_duration_ms: 12,
        tasks: [{ agent_name: 'sales_agent', task_id: 't1', status: 'FAILED', duration_ms: 12, model_calls: 1, tool_calls: 0, evidence_count: 0, error_code: 50081 }],
      }],
    };
    const html = renderToStaticMarkup(
      <ChatMessage message={message} onRetry={() => undefined} onViewRun={() => undefined} />,
    );
    expect(html).toContain('查看运行详情');
    expect(html).toContain('单一 Agent');
    expect(html).not.toContain('SINGLE_AGENT');
  });

  it('成功工具结果禁止盲目重试时展示原因而不是按钮', () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          ...interrupted(),
          can_retry: false,
          retry_denied_reason: '已有成功的工具结果，禁止盲目重试，以免重复执行业务操作。',
          tool_runs: [{
            id: 1, message_id: 180, tool_call_id: 'c1', tool_name: 'propose_action', status: 'SUCCEEDED',
            duration_ms: 1, input_summary: null, output_summary: null, error_code: null, created_at: '', completed_at: '',
          }],
        }}
        onRetry={vi.fn()}
      />,
    );
    expect(html).toContain('已有成功的工具结果');
    expect(html).not.toContain('重新发送');
  });
});
