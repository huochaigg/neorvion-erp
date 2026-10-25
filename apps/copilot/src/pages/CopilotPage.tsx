import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Skeleton } from 'antd';
import { AlertCircle, RotateCcw, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { streamChat } from '@/api/chat';
import { createConversation, getConversation } from '@/api/conversations';
import { listProposals } from '@/api/proposals';
import { ChatComposer } from '@/components/ChatComposer';
import { ChatEmptyState } from '@/components/ChatEmptyState';
import { ChatMessage } from '@/components/ChatMessage';
import { ProposalCard } from '@/components/ProposalCard';
import {
  composeVisibleMessages,
  pendingUserMessage,
  seedConversationWithUser,
  turnHasTerminalAssistant,
} from '@/lib/chatMessages';
import { useCopilotStore } from '@/store';
import type { AgentRun, ConversationDetail, Evidence, Message, StreamEvent, ToolRun } from '@/types';

function requestId() {
  return crypto.randomUUID().replaceAll('-', '');
}

export function CopilotPage() {
  const query = useQueryClient();
  const tenantId = useCopilotStore((s) => s.tenantId);
  const controller = useCopilotStore((s) => s.controller);
  const setController = useCopilotStore((s) => s.setController);
  const selected = useCopilotStore((s) => s.selectedId);
  const setSelected = useCopilotStore((s) => s.setSelectedId);
  const [input, setInput] = useState('');
  const [lastMessage, setLastMessage] = useState('');
  const [draft, setDraft] = useState('');
  const [tools, setTools] = useState<ToolRun[]>([]);
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  const [pendingUser, setPendingUser] = useState<Message | null>(null);
  const [pendingFromIndex, setPendingFromIndex] = useState(0);
  const [pendingConversationId, setPendingConversationId] = useState<number | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);
  const runRef = useRef('');

  const create = useMutation({
    mutationFn: () => createConversation(),
    onSuccess: (row) => {
      void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'copilot-conversations'] });
      setSelected(row.id);
    },
  });
  const detail = useQuery({
    queryKey: ['tenant', tenantId, 'copilot-conversation', selected],
    queryFn: ({ signal }) => getConversation(selected!, signal),
    enabled: selected != null,
  });
  const proposals = useQuery({
    queryKey: ['tenant', tenantId, 'action-proposals', selected],
    queryFn: ({ signal }) => listProposals(signal, selected!),
    enabled: selected != null,
  });

  const pendingForThisChat =
    pendingUser != null && (pendingConversationId == null || pendingConversationId === selected)
      ? pendingUser
      : null;

  useEffect(() => () => useCopilotStore.getState().controller?.abort(), []);
  useEffect(() => {
    if (autoScroll.current) bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [detail.data?.messages, draft, tools, pendingForThisChat]);

  const visible = useMemo(() => {
    const messages = detail.data?.messages ?? [];
    return composeVisibleMessages({
      messages,
      pendingUser: pendingForThisChat,
      pendingFromIndex,
      showLiveAssistant:
        pendingForThisChat != null &&
        (running || !turnHasTerminalAssistant(messages, pendingFromIndex)),
      draft,
      tools,
      evidences,
      analysisStatus,
      agentRun,
    });
  }, [
    agentRun,
    analysisStatus,
    detail.data?.messages,
    draft,
    evidences,
    pendingForThisChat,
    pendingFromIndex,
    running,
    tools,
  ]);

  const handleEvent = (item: StreamEvent, guard: string) => {
    if (runRef.current !== guard) return;
    const data = item.data;
    if (item.event === 'analysis_status') setAnalysisStatus(String(data.message ?? ''));
    if (item.event === 'agent_route')
      setAgentRun({
        id: String(data.agent_run_id ?? 'live'),
        graph_type: String(data.mode ?? '').toUpperCase() === 'MULTI' ? 'MULTI_AGENT' : 'SINGLE_AGENT',
        status: 'RUNNING',
        route_reason: String(data.reason ?? ''),
        total_duration_ms: null,
        tasks: [],
      });
    if (item.event === 'agent_start')
      setAgentRun((value) => {
        const task: AgentRun['tasks'][number] = {
          agent_name: String(data.agent_name ?? ''),
          task_id: String(data.agent_task_id ?? ''),
          status: 'RUNNING',
          duration_ms: null,
          model_calls: 0,
          tool_calls: 0,
          evidence_count: 0,
          error_code: null,
        };
        return value
          ? { ...value, tasks: [...value.tasks.filter((x) => x.task_id !== task.task_id), task] }
          : {
              id: String(data.agent_run_id ?? 'live'),
              graph_type: 'MULTI_AGENT',
              status: 'RUNNING',
              route_reason: null,
              total_duration_ms: null,
              tasks: [task],
            };
      });
    if (item.event === 'agent_end' || item.event === 'agent_error')
      setAgentRun((value) =>
        value
          ? {
              ...value,
              status: item.event === 'agent_error' ? 'DEGRADED' : value.status,
              tasks: value.tasks.map((x) =>
                x.task_id === String(data.agent_task_id ?? '')
                  ? {
                      ...x,
                      status: item.event === 'agent_error' ? 'FAILED' : 'SUCCEEDED',
                      duration_ms: Number(data.duration_ms ?? 0) || null,
                      model_calls: Number(data.model_calls ?? 0),
                      tool_calls: Number(data.tool_calls ?? 0),
                      evidence_count: Number(data.evidence_count ?? 0),
                      error_code: Number(data.error_code ?? 0) || null,
                    }
                  : x,
              ),
            }
          : value,
      );
    if (item.event === 'message') setDraft((value) => value + String(data.delta ?? ''));
    if (item.event === 'tool_start') {
      setTools((value) => [
        ...value,
        {
          id: -value.length - 1,
          message_id: Number(data.message_id ?? 0),
          tool_call_id: String(data.tool_call_id ?? ''),
          tool_name: String(data.name ?? ''),
          status: 'RUNNING',
          duration_ms: null,
          input_summary: String(data.input_summary ?? ''),
          output_summary: null,
          error_code: null,
          created_at: '',
          completed_at: null,
        },
      ]);
    }
    if (item.event === 'tool_end' || item.event === 'tool_error') {
      setTools((value) =>
        value.map((run) =>
          run.tool_call_id === data.tool_call_id
            ? {
                ...run,
                status: item.event === 'tool_end' ? 'SUCCEEDED' : 'FAILED',
                duration_ms: Number(data.duration_ms ?? 0) || null,
                output_summary: String(data.message ?? data.summary ?? '查询完成'),
                error_code: Number(data.code ?? 0) || null,
              }
            : run,
        ),
      );
    }
    if (item.event === 'error') setError(String(data.message ?? '生成失败'));
    if (item.event === 'evidence') {
      setEvidences((value) => [...value, { ...data, access_status: 'ACTIVE' } as unknown as Evidence]);
    }
    if (['proposal_created', 'proposal_updated', 'proposal_validation'].includes(item.event)) {
      void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'action-proposals', selected] });
    }
  };

  const send = async (retryText?: string) => {
    const text = (retryText ?? input).trim();
    if (!text || running) return;
    const guard = requestId();
    const user = pendingUserMessage(text, guard);
    const fromIndex = selected != null ? (detail.data?.messages.length ?? 0) : 0;
    const abort = new AbortController();
    autoScroll.current = true;
    runRef.current = guard;
    setController(abort);
    setLastMessage(text);
    setInput('');
    setDraft('');
    setTools([]);
    setEvidences([]);
    setAnalysisStatus('');
    setAgentRun(null);
    setError('');
    setPendingUser(user);
    setPendingFromIndex(fromIndex);
    setPendingConversationId(selected);
    setRunning(true);

    let conversationId = selected;
    try {
      if (conversationId == null) {
        const created = await create.mutateAsync();
        conversationId = created.id;
        if (runRef.current !== guard) return;
        setPendingConversationId(conversationId);
      }
      const key = ['tenant', tenantId, 'copilot-conversation', conversationId] as const;
      query.setQueryData<ConversationDetail>(key, (old) =>
        seedConversationWithUser(old, conversationId!, user, old?.title),
      );
      if (abort.signal.aborted) {
        setPendingUser(null);
        setPendingConversationId(null);
        return;
      }
      await streamChat({
        conversationId,
        message: text,
        clientRequestId: guard,
        signal: abort.signal,
        onEvent: (event) => handleEvent(event, guard),
      });
    } catch (cause) {
      if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : '生成失败');
      if (conversationId == null) {
        setPendingUser(null);
        setPendingConversationId(null);
        setInput(text);
      }
    } finally {
      if (runRef.current === guard) {
        setRunning(false);
        setController(null);
        if (conversationId != null) {
          void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'copilot-conversation', conversationId] });
          void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'copilot-conversations'] });
        }
      }
    }
  };

  const empty = visible.length === 0 && !running && pendingForThisChat == null;
  const showSkeleton = selected != null && detail.isPending && pendingForThisChat == null && !running;

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      {selected && detail.data?.title && visible.length > 0 ? (
        <header className="flex h-12 shrink-0 items-center justify-center border-b border-[#E2E8F0]/80 bg-white/70 px-16 text-sm font-medium text-[#0F172A] backdrop-blur">
          <span className="truncate">{detail.data.title}</span>
        </header>
      ) : null}
      <section
        onScroll={(event) => {
          const el = event.currentTarget;
          autoScroll.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="copilot-scroll min-h-0 flex-1 overflow-auto px-4 pb-36 pt-6"
      >
        {empty ? (
          <ChatEmptyState disabled={running || create.isPending} onPrompt={(text) => void send(text)} />
        ) : showSkeleton ? (
          <div className="mx-auto max-w-[900px] pt-10">
            <Skeleton active paragraph={{ rows: 8 }} />
          </div>
        ) : (
          <div className="mx-auto flex max-w-[900px] flex-col gap-6">
            {visible.map((message, index) => (
              <ChatMessage key={`${message.role}-${message.id}-${message.request_id}-${index}`} message={message} />
            ))}
            {(proposals.data?.items ?? []).map((proposal) => (
              <ProposalCard
                key={proposal.id}
                value={proposal}
                onChanged={() => void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'action-proposals', selected] })}
              />
            ))}
            <div ref={bottom} />
          </div>
        )}
      </section>
      {error ? (
        <div className="absolute inset-x-0 bottom-28 z-10 mx-auto flex w-[min(100%-2rem,900px)] items-start gap-3 rounded-2xl border border-rose-100 bg-white px-4 py-3 text-sm text-rose-600 shadow-[0_10px_30px_rgba(15,23,42,0.08)]">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1">{error}</div>
          <button
            type="button"
            disabled={!lastMessage || running}
            onClick={() => void send(lastMessage)}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-[#4F46E5] hover:bg-[#EEF2FF] disabled:opacity-40"
          >
            <RotateCcw size={12} />
            重试
          </button>
          <button type="button" onClick={() => setError('')} className="text-[#94A3B8]" aria-label="关闭错误">
            <X size={14} />
          </button>
        </div>
      ) : null}
      <ChatComposer
        value={input}
        running={running}
        disabled={create.isPending}
        placeholder={selected ? '询问 ERP 数据，或指定知识库 ID 查询制度与流程' : '先提问，或选择一个快捷问题开始'}
        onChange={setInput}
        onSend={() => void send()}
        onStop={() => controller?.abort()}
      />
    </div>
  );
}
