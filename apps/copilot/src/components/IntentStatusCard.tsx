import { HelpCircle, ListChecks, PauseCircle } from 'lucide-react';
import type { IntentStatus } from '@/types';

export function IntentStatusCard({
  status,
  onCancel,
}: {
  status?: IntentStatus | null;
  onCancel?: () => void;
}) {
  if (!status?.status_text) return null;
  const pending = Boolean(status.pending) || status.decision === 'INSUFFICIENT' || status.decision === 'AMBIGUOUS';
  const Icon = pending ? HelpCircle : status.pending ? PauseCircle : ListChecks;
  return (
    <div className="mb-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
      <div className="flex items-center gap-2 font-medium text-slate-700">
        <Icon size={14} />
        <span>{status.status_text}</span>
        {status.decision ? <span className="ml-auto font-normal text-slate-400">{status.decision}</span> : null}
      </div>
      {status.missing_slots?.length ? (
        <div className="mt-1 text-amber-700">待补：{status.missing_slots.join('、')}</div>
      ) : null}
      {pending && onCancel ? (
        <button type="button" className="mt-2 text-[11px] text-indigo-600 hover:underline" onClick={onCancel}>
          取消本次补充
        </button>
      ) : null}
    </div>
  );
}
