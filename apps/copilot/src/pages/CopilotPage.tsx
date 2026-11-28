import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Skeleton } from 'antd';
import { AlertCircle, RotateCcw, X } from 'lucide-react';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { cancelChatRun, streamChat, subscribeChatRun } from '@/api/chat';
import { discoverRunnableSkills } from '@/api/ecosystem';
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
  visibleMessageKey,
} from '@/lib/chatMessages';
import {
  canRetryMessage,
  hasRunnableDetails,
  isHeartbeatEvent,
  isTerminalMessageStatus,
  isTerminalSseEvent,
  listenWithReconnect,
  reconnectBudgetKey,
  rememberEventSeq,
  resetReconnectBudget,
  SSE_MAX_RECONNECT_ATTEMPTS,
  type ConnectionState,
} from '@/lib/runConnection';
import { createStreamFrameQueue, shouldApplyStreamEvent, type StreamFrameQueue } from '@/lib/streamUi';
import { useCopilotStore } from '@/store';
import type { AgentRun, ConversationDetail, Evidence, IntentStatus, Message, SkillRunSummary, StreamEvent, ToolRun } from '@/types';

function requestId() {
  return crypto.randomUUID().replaceAll('-', '');
}

export function CopilotPage() {
  const location = useLocation();
  const query = useQueryClient();
  const tenantId = useCopilotStore((s) => s.tenantId);
  const controller = useCopilotStore((s) => s.controller);
  const setController = useCopilotStore((s) => s.setController);
  const selected = useCopilotStore((s) => s.selectedId);
  const setSelected = useCopilotStore((s) => s.setSelectedId);
  const [input, setInput] = useState(
    () => String((location.state as { initialInput?: string } | null)?.initialInput ?? ''),
  );
  const [lastMessage, setLastMessage] = useState('');
  const [draft, setDraft] = useState('');
  const [tools, setTools] = useState<ToolRun[]>([]);
  const [evidences, setEvidences] = useState<Evidence[]>([]);
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null);
  const [skillRuns, setSkillRuns] = useState<SkillRunSummary[]>([]);
  const [intentStatus, setIntentStatus] = useState<IntentStatus | null>(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  const [skillMode, setSkillMode] = useState<'AUTO' | 'MANUAL' | 'NONE'>('NONE');
  const [skillKey, setSkillKey] = useState<string>();
  const [pendingUser, setPendingUser] = useState<Message | null>(null);
  const [pendingFromIndex, setPendingFromIndex] = useState(0);
  const [pendingConversationId, setPendingConversationId] = useState<number | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('DISCONNECTED');
  const [cancelRequested, setCancelRequested] = useState(false);
  const [reconnectGeneration, setReconnectGeneration] = useState(0);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const scroller = useRef<HTMLElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);
  const scrollFrame = useRef(0);
  const runRef = useRef('');
  const pickerTenant = useRef<number | null>(null);
  const queueRef = useRef<StreamFrameQueue | null>(null);
  const selectedRef = useRef(selected);
  const pendingConversationRef = useRef(pendingConversationId);
  const sendInFlightRef = useRef(false);
  const liveMessageIdRef = useRef<number | null>(null);
  const seenSeqRef = useRef<Set<number>>(new Set());
  const terminalRef = useRef(false);
  const lastProgressRef = useRef(Date.now());
  const restoredMessageRef = useRef<number | null>(null);
  useLayoutEffect(() => {
    selectedRef.current = selected;
    pendingConversationRef.current = pendingConversationId;
  }, [selected, pendingConversationId]);

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
  const skillCatalog = useQuery({
    queryKey: ['tenant', tenantId, 'runnable-skill-catalog'],
    queryFn: ({ signal }) => discoverRunnableSkills(signal),
    enabled: tenantId != null,
  });

  useEffect(() => {
    if (!skillCatalog.data || pickerTenant.current === tenantId) return;
    pickerTenant.current = tenantId;
    setSkillKey(undefined);
    setSkillMode(skillCatalog.data.default_mode);
  }, [skillCatalog.data, tenantId]);

  const pendingForThisChat =
    pendingUser != null && (pendingConversationId == null || pendingConversationId === selected)
      ? pendingUser
      : null;
  const runningAssistant = useMemo(
    () =>
      [...(detail.data?.messages ?? [])]
        .reverse()
        .find((item) => item.role === 'assistant' && item.status === 'RUNNING') ?? null,
    [detail.data?.messages],
  );

  useEffect(() => {
    return () => {
      queueRef.current?.close();
      useCopilotStore.getState().controller?.abort();
      if (scrollFrame.current) cancelAnimationFrame(scrollFrame.current);
    };
  }, []);

  useEffect(() => {
    if (pendingConversationId != null && selected != null && selected !== pendingConversationId) {
      queueRef.current?.close();
      useCopilotStore.getState().controller?.abort();
    }
  }, [pendingConversationId, selected]);

  useEffect(() => {
    if (connection !== 'CONNECTED' && connection !== 'WAITING_TOO_LONG') return;
    const timer = window.setInterval(() => {
      if (Date.now() - lastProgressRef.current >= 30_000) {
        setConnection('WAITING_TOO_LONG');
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [connection]);

  useEffect(() => {
    const live = runningAssistant;
    if (sendInFlightRef.current || live == null || selected == null) return;
    const abort = new AbortController();
    const guard = `restore-${live.id}-${reconnectGeneration}`;
    const budgetKey = reconnectBudgetKey(selected, live.id);
    const queue = createStreamFrameQueue({
      onEvent: (event) => handleEvent(event, guard),
    });
    runRef.current = guard;
    seenSeqRef.current = new Set();
    terminalRef.current = false;
    liveMessageIdRef.current = live.id;
    lastProgressRef.current = Date.now();
    restoredMessageRef.current = live.id;
    queueRef.current?.close();
    queueRef.current = queue;
    setController(abort);
    setPendingConversationId(selected);
    setDraft(live.content || '');
    setTools(live.tool_runs ?? []);
    setEvidences(live.evidences ?? []);
    setAgentRun(live.agent_runs?.[0] ?? null);
    setSkillRuns(live.skill_runs ?? []);
    setIntentStatus(live.intent_status ?? null);
    setRunning(true);
    setConnection('CONNECTING');
    void listenWithReconnect({
      signal: abort.signal,
      budgetKey,
      shouldRetry: () => !terminalRef.current && !abort.signal.aborted,
      onState: setConnection,
      onAttempt: (attempt) => setReconnectAttempt(attempt),
      subscribe: (signal) =>
        subscribeChatRun({
          conversationId: selected,
          messageId: live.id,
          after: live.last_event_seq ?? 0,
          signal,
          onEvent: (event) => {
            queue.push(event);
          },
        }),
    }).finally(() => {
      if (!abort.signal.aborted) {
        queue.flush();
      }
      queue.close();
      if (queueRef.current === queue) queueRef.current = null;
      if (runRef.current === guard) {
        setRunning(false);
        setController(null);
        void query.invalidateQueries({
          queryKey: ['tenant', tenantId, 'copilot-conversation', selected],
        });
      }
    });
    return () => {
      abort.abort();
    };
  }, [query, runningAssistant?.id, selected, tenantId, reconnectGeneration]);

  const visible = useMemo(() => {
    const messages = detail.data?.messages ?? [];
    return composeVisibleMessages({
      messages,
      pendingUser: pendingForThisChat,
      pendingFromIndex,
      showLiveAssistant:
        (pendingForThisChat != null &&
          (running || !turnHasTerminalAssistant(messages, pendingFromIndex))) ||
        runningAssistant != null,
      draft,
      tools,
      evidences,
      analysisStatus,
      agentRun,
      skillRuns,
      intentStatus,
      connectionState: connection,
      connectionAttempt: reconnectAttempt,
      connectionMaxAttempts: SSE_MAX_RECONNECT_ATTEMPTS,
    });
  }, [
    agentRun,
    analysisStatus,
    connection,
    detail.data?.messages,
    draft,
    evidences,
    pendingForThisChat,
    pendingFromIndex,
    running,
    tools,
    skillRuns,
    intentStatus,
    reconnectAttempt,
  ]);

  useEffect(() => {
    if (!autoScroll.current || scrollFrame.current) return;
    scrollFrame.current = requestAnimationFrame(() => {
      scrollFrame.current = 0;
      const el = scroller.current;
      if (!el || !autoScroll.current) return;
      el.scrollTop = el.scrollHeight;
    });
  }, [agentRun, draft, pendingForThisChat, running, skillRuns, tools, visible.length]);

  const handleEvent = (item: StreamEvent, guard: string) => {
    if (
      !shouldApplyStreamEvent({
        runId: guard,
        activeRunId: runRef.current,
        pendingConversationId: pendingConversationRef.current,
        selectedConversationId: selectedRef.current,
      })
    ) {
      return;
    }
    if (isHeartbeatEvent(item.event)) {
      setConnection((state) =>
        state === 'WAITING_TOO_LONG' || state === 'RECONNECT_FAILED' ? state : 'CONNECTED',
      );
      return;
    }
    const seq = item.data.sequence ?? item.data.event_id;
    if (!rememberEventSeq(seenSeqRef.current, seq)) return;
    const data = item.data;
    const messageId = Number(data.message_id ?? 0);
    if (messageId > 0) liveMessageIdRef.current = messageId;
    if (item.event === 'run_status') return;
    if (!isHeartbeatEvent(item.event) && !isTerminalSseEvent(item.event)) {
      lastProgressRef.current = Date.now();
      setConnection('CONNECTED');
    }
    if (isTerminalSseEvent(item.event)) {
      const eventStatus = String(data.status ?? '');
      terminalRef.current = eventStatus ? isTerminalMessageStatus(eventStatus) : true;
      const targetId = messageId > 0 ? messageId : liveMessageIdRef.current;
      if (terminalRef.current && selectedRef.current != null && targetId != null && targetId > 0) {
        const key = ['tenant', tenantId, 'copilot-conversation', selectedRef.current] as const;
        query.setQueryData<ConversationDetail>(key, (old) => {
          if (!old) return old;
          return {
            ...old,
            messages: old.messages.map((row) =>
              row.id === targetId
                ? {
                    ...row,
                    status: eventStatus || row.status,
                    content: String(data.answer ?? row.content),
                    can_retry: Boolean(data.can_retry),
                    can_reconnect: Boolean(data.can_reconnect),
                    can_cancel: Boolean(data.can_cancel),
                    interrupt_reason: data.reason != null ? String(data.reason) : row.interrupt_reason,
                    live: false,
                  }
                : row,
            ),
          };
        });
      }
    }
    if (item.event === 'skill_selected' || item.event === 'skill_start') {
      setSkillRuns((value) => {
        const id = Number(data.skill_run_id ?? 0);
        const next = {
          id,
          skill_id: Number(data.skill_id ?? 0),
          skill_key: String(data.skill_key ?? ''),
          skill_name: String(data.skill_name ?? ''),
          skill_version: Number(data.skill_version ?? 0),
          status: item.event === 'skill_start' ? 'RUNNING' : 'SELECTED',
          selection_method: String(data.selection_method ?? '') || null,
          selection_reason: String(data.selection_reason ?? '') || null,
          plan_id: Number(data.plan_id ?? 0) || null,
          plan_step_key: String(data.step_key ?? '') || null,
          loaded_resources: value.find((row) => row.id === id)?.loaded_resources ?? [],
          safe_error: null,
        };
        return [...value.filter((row) => row.id !== id), next];
      });
    }
    if (item.event === 'skill_input_required') {
      setSkillRuns([{
        id: 0,
        skill_id: 0,
        skill_key: String(data.skill_key ?? ''),
        skill_name: String(data.skill_key ?? '参数补全'),
        skill_version: 0,
        status: String(data.status ?? 'COLLECTING_INPUT'),
        selection_method: null,
        missing_fields: Array.isArray(data.missing_fields) ? data.missing_fields.map(String) : [],
        loaded_resources: [],
        safe_error: null,
      }]);
    }
    if (item.event === 'skill_resource_loaded') {
      setSkillRuns((value) => value.map((run) => ({
        ...run,
        loaded_resources: [...new Set([...run.loaded_resources, String(data.resource_path ?? '')])].filter(Boolean),
      })));
    }
    if (item.event === 'skill_done' || item.event === 'skill_error' || item.event === 'skill_plan_done' || item.event === 'skill_plan_error') {
      setSkillRuns((value) => value.map((run) => ({
        ...run,
        status: item.event === 'skill_done' || item.event === 'skill_plan_done' ? String(data.status ?? 'SUCCEEDED') : 'FAILED',
        safe_error: item.event === 'skill_error' || item.event === 'skill_plan_error' ? String(data.message ?? 'Skill 执行失败') : null,
      })));
    }
    if (item.event === 'intent_resolved' || item.event === 'intent_clarification') {
      setIntentStatus({
        resolution_id: String(data.resolution_id ?? ''),
        status_text: String(data.status_text ?? data.clarification ?? ''),
        decision: String(data.decision ?? ''),
        intents: Array.isArray(data.intents) ? data.intents.map(String) : [],
        problem_types: Array.isArray(data.problem_types) ? data.problem_types.map(String) : [],
        missing_slots: Array.isArray(data.missing_slots) ? data.missing_slots.map(String) : [],
        pending: Boolean(data.pending) || data.status === 'COLLECTING' || data.status === 'CLARIFY',
        clarification: data.clarification ? String(data.clarification) : null,
        agents: Array.isArray(data.agents) ? data.agents.map(String) : [],
        skills: Array.isArray(data.skills) ? data.skills.map(String) : [],
        mode: data.mode ? String(data.mode) : undefined,
      });
    }
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
      void query.invalidateQueries({
        queryKey: ['tenant', tenantId, 'action-proposals', selectedRef.current],
      });
    }
  };

  const send = async (retryText?: string, retryOfMessageId?: number) => {
    const text = (retryText ?? input).trim();
    if (!text || running) return;
    const guard = requestId();
    const retrying = retryOfMessageId != null && retryOfMessageId > 0;
    const user = pendingUserMessage(text, guard);
    const fromIndex = selected != null ? (detail.data?.messages.length ?? 0) : 0;
    const abort = new AbortController();
    autoScroll.current = true;
    runRef.current = guard;
    sendInFlightRef.current = true;
    liveMessageIdRef.current = null;
    seenSeqRef.current = new Set();
    terminalRef.current = false;
    lastProgressRef.current = Date.now();
    setConnection('CONNECTING');
    setCancelRequested(false);
    queueRef.current?.close();
    const queue = createStreamFrameQueue({
      onEvent: (event) => handleEvent(event, guard),
    });
    queueRef.current = queue;
    setController(abort);
    setLastMessage(text);
    setInput('');
    setDraft('');
    setTools([]);
    setEvidences([]);
    setAnalysisStatus('');
    setAgentRun(null);
    setSkillRuns([]);
    setIntentStatus(null);
    setError('');
    setPendingUser(retrying ? null : user);
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
      if (!retrying) {
        query.setQueryData<ConversationDetail>(key, (old) =>
          seedConversationWithUser(old, conversationId!, user, old?.title),
        );
      }
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
        onEvent: (event) => {
          queue.push(event);
        },
        skillMode,
        skillKey,
        retryOfMessageId: retrying ? retryOfMessageId : undefined,
      });
    } catch (cause) {
      if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : '生成失败');
      if (conversationId == null) {
        setPendingUser(null);
        setPendingConversationId(null);
        setInput(text);
      }
    } finally {
      if (abort.signal.aborted) {
        queue.close();
      } else {
        queue.flush();
        queue.close();
      }
      if (queueRef.current === queue) queueRef.current = null;
      sendInFlightRef.current = false;
      if (runRef.current === guard) {
        setRunning(false);
        setController(null);
        if (!terminalRef.current) setConnection('DISCONNECTED');
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
        ref={scroller}
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
              <ChatMessage
                key={visibleMessageKey(message, index)}
                message={
                  cancelRequested && message.status === 'RUNNING'
                    ? { ...message, interrupt_reason: message.interrupt_reason ?? 'cancel_requested' }
                    : message
                }
                onCancelIntent={message.id < 0 && intentStatus?.pending ? () => void send('取消') : undefined}
                onRetry={
                  canRetryMessage(message)
                    ? () => {
                        const prior = visible[index - 1];
                        if (prior?.role === 'user') void send(prior.content, message.id);
                      }
                    : undefined
                }
                onReconnect={
                  selected != null && message.id > 0
                    ? () => {
                        resetReconnectBudget(reconnectBudgetKey(selected, message.id));
                        setReconnectAttempt(0);
                        setConnection('CONNECTING');
                        setReconnectGeneration((value) => value + 1);
                      }
                    : undefined
                }
                onCancelRun={
                  selected != null && message.id > 0
                    ? () => {
                        setCancelRequested(true);
                        void cancelChatRun(selected, message.id)
                          .catch(() => undefined)
                          .finally(() => {
                            void query.invalidateQueries({
                              queryKey: ['tenant', tenantId, 'copilot-conversation', selected],
                            });
                          });
                      }
                    : undefined
                }
                onViewRun={
                  hasRunnableDetails(message)
                    ? () => {
                        document.getElementById(`copilot-run-detail-${message.id}`)?.scrollIntoView({
                          behavior: 'smooth',
                          block: 'start',
                        });
                      }
                    : undefined
                }
              />
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
        onStop={() => {
          setCancelRequested(true);
          const conversationId = selected ?? pendingConversationId;
          const messageId = liveMessageIdRef.current;
          if (conversationId != null && messageId != null && messageId > 0) {
            void cancelChatRun(conversationId, messageId).catch(() => undefined);
          }
          queueRef.current?.close();
          controller?.abort();
        }}
        skillMode={skillMode}
        skillKey={skillKey}
        skills={skillCatalog.data?.items ?? []}
        autoAvailable={Boolean(skillCatalog.data?.auto_available)}
        onSkillModeChange={(mode) => {
          setSkillMode(mode);
          if (mode === 'MANUAL' && !skillKey) setSkillKey(skillCatalog.data?.items[0]?.skill_key);
        }}
        onSkillKeyChange={setSkillKey}
      />
    </div>
  );
}
