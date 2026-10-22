import { LoaderCircle, Send, Square } from 'lucide-react';

export function ChatComposer({
  value,
  running,
  disabled,
  placeholder,
  onChange,
  onSend,
  onStop,
}: {
  value: string;
  running: boolean;
  disabled?: boolean;
  placeholder: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
}) {
  const canSend = Boolean(value.trim()) && !disabled && !running;
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#F8FAFC] via-[#F8FAFC]/95 to-transparent px-4 pb-5 pt-10">
      <div className="pointer-events-auto mx-auto flex w-full max-w-[900px] items-end gap-2 rounded-[20px] border border-[#E2E8F0] bg-white p-3 shadow-[0_12px_40px_rgba(15,23,42,0.08)]">
        <textarea
          value={value}
          disabled={disabled || running}
          rows={1}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              if (canSend) onSend();
            }
          }}
          className="max-h-36 min-h-[44px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 text-[#0F172A] outline-none placeholder:text-[#94A3B8] disabled:cursor-not-allowed"
        />
        {running ? (
          <button
            type="button"
            onClick={onStop}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#FECACA] bg-[#FEF2F2] text-[#DC2626] transition hover:bg-[#FEE2E2]"
            aria-label="停止生成"
          >
            <Square size={14} fill="currentColor" />
          </button>
        ) : (
          <button
            type="button"
            disabled={!canSend}
            onClick={onSend}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#4F8CFF] to-[#8B5CF6] text-white shadow-[0_8px_18px_rgba(99,102,241,0.35)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            aria-label="发送"
          >
            {disabled ? <LoaderCircle size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        )}
      </div>
    </div>
  );
}
