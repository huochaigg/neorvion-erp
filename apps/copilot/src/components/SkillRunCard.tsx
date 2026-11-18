import { BookOpen, CheckCircle2, LoaderCircle, XCircle } from 'lucide-react';
import type { SkillRunSummary } from '@/types';

export function SkillRunCard({ runs }: { runs: SkillRunSummary[] }) {
  if (!runs.length) return null;
  return (
    <div className="mb-3 space-y-2">
      {runs.map((run) => {
        const Icon = run.status === 'SUCCEEDED' ? CheckCircle2 : run.status === 'FAILED' ? XCircle : LoaderCircle;
        return (
          <div key={`${run.id}-${run.skill_key}`} className="rounded-xl border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-xs text-slate-600">
            <div className="flex items-center gap-2 font-medium text-indigo-700">
              <Icon size={14} className={run.status === 'RUNNING' ? 'animate-spin' : ''} />
              <span>{run.skill_name}</span>
              <span className="font-normal text-slate-400">v{run.skill_version}</span>
              <span className="ml-auto">{run.status}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              <span>SkillRun #{run.id}</span>
              {run.selection_method ? <span>{run.selection_method}</span> : null}
              {run.loaded_resources.map((item) => (
                <span key={item} className="inline-flex items-center gap-1"><BookOpen size={11} />{item}</span>
              ))}
            </div>
            {run.safe_error ? <div className="mt-1 text-rose-600">{run.safe_error}</div> : null}
          </div>
        );
      })}
    </div>
  );
}
