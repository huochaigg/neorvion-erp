import { BookOpen, Database, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import type { Evidence } from '@/types';

export function EvidenceCard({ items }: { items: Evidence[] }) {
  const [selected, setSelected] = useState<Evidence | null>(null);
  if (!items.length) return null;
  return (
    <div className="mt-4 border-t border-[#E2E8F0] pt-3">
      <div className="mb-2 text-xs font-medium text-[#64748B]">本次回答依据</div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <button key={item.citation_id} type="button" onClick={() => setSelected(item)} className="inline-flex max-w-full items-center gap-2 rounded-lg border border-[#E2E8F0] bg-white px-2.5 py-1.5 text-left text-xs text-[#475569] hover:border-[#A5B4FC]">
            {item.source_type === 'ERP' ? <Database size={13} /> : <BookOpen size={13} />}
            <span className="font-semibold text-[#4F46E5]">[{item.citation_id}]</span>
            <span className="truncate">{item.title}</span>
          </button>
        ))}
      </div>
      {selected ? (
        <div role="dialog" aria-label="证据详情" className="mt-3 rounded-xl border border-[#C7D2FE] bg-[#F8FAFC] p-3 text-sm text-[#334155]">
          <div className="flex items-start justify-between gap-3">
            <div className="font-medium">[{selected.citation_id}] {selected.title}</div>
            <button type="button" onClick={() => setSelected(null)} className="text-xs text-[#64748B]">关闭</button>
          </div>
          {selected.access_status !== 'ACTIVE' ? (
            <div className="mt-2 flex items-center gap-2 text-amber-700"><ShieldAlert size={14} />来源状态：{selected.access_status}</div>
          ) : null}
          {selected.excerpt ? <p className="mt-2 whitespace-pre-wrap break-words leading-6">{selected.excerpt}</p> : <p className="mt-2 text-[#64748B]">当前无权查看或来源已不可用。</p>}
        </div>
      ) : null}
    </div>
  );
}
