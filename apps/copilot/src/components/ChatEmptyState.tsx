import { ClipboardList, Headphones, Package, ShoppingCart } from 'lucide-react';
import { BrandMark } from '@/components/BrandMark';

const QUICK_PROMPTS = [
  { icon: ShoppingCart, text: '帮我分析近期销售订单' },
  { icon: Package, text: '查询库存不足的商品' },
  { icon: ClipboardList, text: '查看待处理采购订单' },
  { icon: Headphones, text: '分析近期售后情况' },
] as const;

export function ChatEmptyState({
  disabled,
  onPrompt,
}: {
  disabled?: boolean;
  onPrompt: (text: string) => void;
}) {
  return (
    <div className="copilot-fade mx-auto flex min-h-full w-full max-w-[900px] flex-col items-center justify-center px-6 py-10">
      <BrandMark size={56} />
      <h1 className="mt-6 text-center text-[28px] font-semibold tracking-tight text-[#0F172A]">
        今天有什么可以帮你？
      </h1>
      <p className="mt-2 max-w-lg text-center text-sm leading-6 text-[#64748B]">
        查询订单、分析库存、了解业务，让 AI 帮你处理日常工作。
      </p>
      <div className="mt-8 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.text}
            type="button"
            disabled={disabled}
            onClick={() => onPrompt(item.text)}
            className="group flex items-start gap-3 rounded-[16px] border border-[#E2E8F0] bg-white px-4 py-4 text-left shadow-[0_6px_18px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-[#C7D2FE] hover:shadow-[0_10px_24px_rgba(99,102,241,0.12)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#EEF2FF] text-[#6366F1] transition group-hover:bg-gradient-to-br group-hover:from-[#4F8CFF] group-hover:to-[#8B5CF6] group-hover:text-white">
              <item.icon size={18} />
            </span>
            <span className="text-sm font-medium leading-6 text-[#0F172A]">{item.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
