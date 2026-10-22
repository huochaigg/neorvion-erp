import { History, ImagePlay, PenLine } from 'lucide-react';
import { BrandMark } from '@/components/BrandMark';

const COPY = {
  ads: {
    icon: ImagePlay,
    title: 'AI 广告创作',
    subtitle: '广告图片生成与广告文案生成即将在此聚合上线。',
    items: ['根据商品与卖点生成广告图', '产出可用于投放的广告文案', '与生成历史联动回看素材'],
  },
  history: {
    icon: History,
    title: '生成历史',
    subtitle: '图片与文案生成记录将集中在这里查看，不会用示例数据冒充已完成。',
    items: ['回看广告图与文案版本', '按时间和会话筛选记录', '把可用素材带回创作流程'],
  },
} as const;

export function ComingSoon({ kind }: { kind: keyof typeof COPY }) {
  const item = COPY[kind];
  const Icon = item.icon;
  return (
    <div className="flex h-full min-h-0 items-center justify-center bg-[#F8FAFC] px-6">
      <div className="copilot-fade w-full max-w-xl rounded-[20px] border border-[#E2E8F0] bg-white p-10 text-center shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#EEF2FF] text-[#6366F1]">
          <Icon size={26} />
        </div>
        <div className="mb-2 flex items-center justify-center gap-2">
          <BrandMark size={28} />
          <h1 className="text-[22px] font-semibold tracking-tight text-[#0F172A]">{item.title}</h1>
        </div>
        <p className="text-sm leading-6 text-[#64748B]">{item.subtitle}</p>
        <div className="mt-6 space-y-2 text-left">
          {item.items.map((line) => (
            <div
              key={line}
              className="flex items-center gap-3 rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] px-4 py-3 text-sm text-[#334155]"
            >
              <PenLine size={16} className="shrink-0 text-[#6366F1]" />
              {line}
            </div>
          ))}
        </div>
        <div className="mt-8 inline-flex rounded-full bg-[#EEF2FF] px-4 py-1.5 text-xs font-medium text-[#6366F1]">
          功能正在建设中
        </div>
      </div>
    </div>
  );
}
