import { Tag } from 'antd';
import type { ReactNode } from 'react';
import { isEmbeddedInWujie } from '@/lib/runtime';

interface KnowledgeLayoutProps {
  children: ReactNode;
}

export function KnowledgeLayout({ children }: KnowledgeLayoutProps) {
  const embedded = isEmbeddedInWujie();
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-white">
      {embedded ? null : (
        <header className="flex shrink-0 items-center justify-between bg-[#102a43] px-4 py-3">
          <span className="text-sm font-semibold text-white">Neorvion Knowledge · 独立运行</span>
          <Tag color="gold">开发调试</Tag>
        </header>
      )}
      <div className="min-h-0 flex-1 overflow-hidden px-5 pb-4 pt-4">{children}</div>
    </div>
  );
}
