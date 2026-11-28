import { memo } from 'react';
import { SafeMarkdown } from '@/components/SafeMarkdown';
import { ToolRunCard } from '@/components/ToolRunCard';
import { EvidenceCard } from '@/components/EvidenceCard';
import type { Message } from '@/types';
import { AgentExecutionPanel } from '@/components/AgentExecutionPanel';
import { SkillRunCard } from '@/components/SkillRunCard';
import { IntentStatusCard } from '@/components/IntentStatusCard';
import {
  canRetryMessage,
  hasRunnableDetails,
  hasVisibleAgentTrace,
  runStatusHint,
  runStatusLabel,
} from '@/lib/runConnection';

export const ChatMessage = memo(function ChatMessage({
  message,
  onCancelIntent,
  onRetry,
  onReconnect,
  onCancelRun,
  onViewRun,
}: {
  message: Message;
  onCancelIntent?: () => void;
  onRetry?: () => void;
  onReconnect?: () => void;
  onCancelRun?: () => void;
  onViewRun?: () => void;
}) {
  const isUser = message.role === 'user';
  const retryAllowed = canRetryMessage(message);
  const statusText = runStatusLabel({
    status: message.status,
    connection: message.connection_state,
    debugExecution: message.debug_execution,
    interruptReason: message.interrupt_reason,
    cancelRequested: message.interrupt_reason === 'cancel_requested',
    reconnectAttempt: message.connection_attempt,
    reconnectMaxAttempts: message.connection_max_attempts,
    graphType: message.agent_runs?.[0]?.graph_type,
  });
  const hint = runStatusHint({
    status: message.status,
    canRetry: retryAllowed,
    retryDeniedReason: message.retry_denied_reason,
  });
  const showDots =
    message.status === 'RUNNING' &&
    !message.content &&
    (message.connection_state === 'CONNECTED' ||
      message.connection_state === 'CONNECTING' ||
      message.connection_state == null);
  const abnormal = ['FAILED', 'INTERRUPTED', 'TIMED_OUT', 'CANCELLED'].includes(message.status);
  const connectionFailed =
    message.status === 'RUNNING' &&
    (message.connection_state === 'RECONNECT_FAILED' || message.connection_state === 'DISCONNECTED');
  const visibleRuns = (message.agent_runs ?? []).filter(hasVisibleAgentTrace);
  const showDetails = hasRunnableDetails(message);
  const showReconnect = connectionFailed && (message.can_reconnect || message.status === 'RUNNING') && onReconnect;
  const showRetry = abnormal && retryAllowed && onRetry;
  const showCancel = connectionFailed && message.can_cancel && onCancelRun;
  const showViewRun = (abnormal || connectionFailed) && showDetails && onViewRun;
  return (
    <div className={`copilot-fade flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[min(100%,720px)] ${isUser ? '' : 'w-full'}`}>
        {isUser ? (
          <div className="rounded-[20px] bg-[#EEF2FF] px-4 py-3 text-[15px] leading-7 text-[#0F172A] shadow-[0_6px_16px_rgba(99,102,241,0.08)]">
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
        ) : (
          <div>
            {statusText && (message.status === 'RUNNING' || abnormal) ? (
              <div className={`mb-1 text-sm ${abnormal || message.connection_state === 'RECONNECT_FAILED' ? 'text-rose-500' : 'text-[#6366F1]'}`}>
                {statusText}
              </div>
            ) : null}
            {hint ? <div className="mb-2 text-xs text-[#64748B]">{hint}</div> : null}
            <div id={showDetails ? `copilot-run-detail-${message.id}` : undefined}>
              <IntentStatusCard status={message.intent_status} onCancel={onCancelIntent} />
              <SkillRunCard runs={message.skill_runs ?? []} />
              <AgentExecutionPanel runs={visibleRuns} toolRuns={message.tool_runs} />
              {message.tool_runs.length ? <ToolRunCard runs={message.tool_runs} /> : null}
              {message.analysis_status && message.status === 'RUNNING' ? <div className="mb-2 text-xs text-[#6366F1]">{message.analysis_status}</div> : null}
              {message.content ? <SafeMarkdown text={message.content} /> : null}
              <EvidenceCard items={message.evidences ?? []} />
            </div>
            {showDots ? (
              <div className="flex items-center gap-1 py-2 text-[#6366F1]">
                <span className="copilot-dot h-1.5 w-1.5 rounded-full bg-current" />
                <span className="copilot-dot h-1.5 w-1.5 rounded-full bg-current" />
                <span className="copilot-dot h-1.5 w-1.5 rounded-full bg-current" />
              </div>
            ) : null}
            {showReconnect || showRetry || showCancel || showViewRun ? (
              <div className="mt-2 flex flex-wrap gap-3">
                {showReconnect ? (
                  <button type="button" onClick={onReconnect} className="text-xs font-medium text-[#4F46E5] hover:underline">
                    重新连接
                  </button>
                ) : null}
                {showRetry ? (
                  <button type="button" onClick={onRetry} className="text-xs font-medium text-[#4F46E5] hover:underline">
                    重新发送
                  </button>
                ) : null}
                {showViewRun ? (
                  <button type="button" onClick={onViewRun} className="text-xs font-medium text-[#4F46E5] hover:underline">
                    查看运行详情
                  </button>
                ) : null}
                {showCancel ? (
                  <button type="button" onClick={onCancelRun} className="text-xs font-medium text-rose-500 hover:underline">
                    取消任务
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
});
