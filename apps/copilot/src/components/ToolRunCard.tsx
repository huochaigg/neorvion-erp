import { Check, ChevronDown, LoaderCircle, Wrench, X } from 'lucide-react';
import { useState } from 'react';
import type { ToolRun } from '@/types';

const LABELS: Record<string, string> = {
  get_sales_order: '查询销售订单',
  list_sales_orders: '查询销售订单',
  get_inventory: '查询库存',
  get_product: '查询商品',
  search_products: '搜索商品',
  list_purchase_orders: '查询采购订单',
  get_warehouse: '查询仓库',
  get_after_sale: '查询售后',
};

function StatusIcon({ status }: { status: string }) {
  if (status === 'SUCCEEDED') return <Check size={14} className="text-emerald-600" />;
  if (status === 'FAILED') return <X size={14} className="text-rose-500" />;
  return <LoaderCircle size={14} className="animate-spin text-[#6366F1]" />;
}

export function ToolRunCard({ runs }: { runs: ToolRun[] }) {
  const [open, setOpen] = useState(true);
  if (!runs.length) return null;
  const running = runs.some((item) => item.status === 'RUNNING');
  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-[#E2E8F0] bg-[#F8FAFC]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-[#64748B] transition hover:bg-white/70"
      >
        <span className="flex items-center gap-2">
          <Wrench size={14} className="text-[#6366F1]" />
          {running ? '正在查询业务数据' : `已完成 ${runs.length} 项工具调用`}
        </span>
        <ChevronDown size={14} className={`transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open ? (
        <div className="space-y-2 border-t border-[#E2E8F0] px-3 py-2">
          {runs.map((run) => (
            <div key={run.tool_call_id} className="rounded-lg bg-white px-3 py-2">
              <div className="flex items-center gap-2 text-sm text-[#0F172A]">
                <StatusIcon status={run.status} />
                <span className="font-medium">{LABELS[run.tool_name] ?? run.tool_name}</span>
                {run.duration_ms != null ? (
                  <span className="text-xs text-[#94A3B8]">{run.duration_ms}ms</span>
                ) : null}
              </div>
              {run.output_summary ? (
                <p className="mt-1 text-xs leading-5 text-[#64748B]">{run.output_summary}</p>
              ) : run.input_summary ? (
                <p className="mt-1 truncate text-xs text-[#94A3B8]">{run.input_summary}</p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
