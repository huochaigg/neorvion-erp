import { useQuery } from '@tanstack/react-query';
import { Result, Spin } from 'antd';
import { PanelLeftOpen } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { api, unwrap } from '@/api/client';
import { Sidebar } from '@/components/Sidebar';
import { ModelStatusBanner } from '@/components/ModelStatusBanner';
import { useCopilotStore } from '@/store';
import type { ApiResponse } from '@neorvion/shared';

export function WorkbenchLayout() {
  const tenantId = useCopilotStore((s) => s.tenantId);
  const collapsed = useCopilotStore((s) => s.sidebarCollapsed);
  const setCollapsed = useCopilotStore((s) => s.setSidebarCollapsed);
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 900px)').matches);
  const [mobileOpen, setMobileOpen] = useState(false);
  const permission = useQuery({
    queryKey: ['tenant', tenantId, 'copilot-me'],
    queryFn: ({ signal }) => unwrap(api.get<ApiResponse<{ permissions: string[] }>>('/api/v1/me', { signal })),
    enabled: tenantId != null,
  });

  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)');
    const onChange = () => {
      setNarrow(media.matches);
      if (media.matches) setMobileOpen(false);
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  if (tenantId == null) {
    return <Result status="warning" title="缺少企业上下文" subTitle="请从主应用打开 ERP Copilot" />;
  }
  if (permission.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-[#F8FAFC]">
        <Spin />
      </div>
    );
  }
  if (permission.isError) {
    return (
      <Result
        status="error"
        title="Copilot 服务不可用"
        subTitle={permission.error instanceof Error ? permission.error.message : '无法加载身份与权限'}
      />
    );
  }
  if (!permission.data?.permissions.includes('copilot:use')) {
    return <Result status="403" title="无权限" subTitle="当前企业身份缺少 copilot:use 权限" />;
  }

  const hideSidebar = narrow && !mobileOpen;
  return (
    <div className="relative flex h-full min-h-0 bg-[#F8FAFC]">
      {hideSidebar ? null : (
        <>
          {narrow ? (
            <button
              type="button"
              className="absolute inset-0 z-20 bg-slate-900/20"
              aria-label="关闭导航"
              onClick={() => setMobileOpen(false)}
            />
          ) : null}
          <div className={narrow ? 'absolute inset-y-0 left-0 z-30' : 'relative z-10'}>
            <Sidebar
              collapsed={!narrow && collapsed}
              narrow={narrow}
              onToggle={() => (narrow ? setMobileOpen(false) : setCollapsed((value) => !value))}
              onNavigate={narrow ? () => setMobileOpen(false) : undefined}
            />
          </div>
        </>
      )}
      <main className="relative flex min-w-0 flex-1 flex-col">
        {hideSidebar ? (
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="absolute left-4 top-4 z-10 flex h-10 w-10 items-center justify-center rounded-xl border border-[#E2E8F0] bg-white text-[#64748B] shadow-sm"
            aria-label="打开导航"
          >
            <PanelLeftOpen size={18} />
          </button>
        ) : null}
        <ModelStatusBanner />
        <div className="min-h-0 flex-1"><Outlet /></div>
      </main>
    </div>
  );
}
