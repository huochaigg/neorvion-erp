import { SafeMarkdown } from '@/components/SafeMarkdown';
import { ToolRunCard } from '@/components/ToolRunCard';
import type { Message } from '@/types';

export function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  return (
    <div className={`copilot-fade flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[min(100%,720px)] ${isUser ? '' : 'w-full'}`}>
        {isUser ? (
          <div className="rounded-[20px] bg-[#EEF2FF] px-4 py-3 text-[15px] leading-7 text-[#0F172A] shadow-[0_6px_16px_rgba(99,102,241,0.08)]">
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
        ) : (
          <div>
            {message.tool_runs.length ? <ToolRunCard runs={message.tool_runs} /> : null}
            {message.content ? <SafeMarkdown text={message.content} /> : null}
            {message.status === 'RUNNING' && !message.content ? (
              <div className="flex items-center gap-1 py-2 text-[#6366F1]">
                <span className="copilot-dot h-1.5 w-1.5 rounded-full bg-current" />
                <span className="copilot-dot h-1.5 w-1.5 rounded-full bg-current" />
                <span className="copilot-dot h-1.5 w-1.5 rounded-full bg-current" />
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
