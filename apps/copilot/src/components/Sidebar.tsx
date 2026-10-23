import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Input, Modal, Skeleton } from 'antd';
import {
  Bot,
  History,
  ImagePlay,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Search,
  Trash2,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  createConversation,
  deleteConversation,
  listConversations,
  renameConversation,
} from '@/api/conversations';
import { BrandMark } from '@/components/BrandMark';
import { useCopilotStore } from '@/store';

const NAV = [
  { to: '/chat', label: 'ERP 智能助手', icon: Bot, live: true },
  { to: '/ads', label: 'AI 广告创作', icon: ImagePlay, live: false },
  { to: '/history', label: '生成历史', icon: History, live: false },
] as const;

export function Sidebar({
  collapsed,
  narrow,
  onToggle,
  onNavigate,
}: {
  collapsed: boolean;
  narrow: boolean;
  onToggle: () => void;
  onNavigate?: () => void;
}) {
  const query = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const tenantId = useCopilotStore((s) => s.tenantId);
  const selectedId = useCopilotStore((s) => s.selectedId);
  const setSelectedId = useCopilotStore((s) => s.setSelectedId);
  const [keyword, setKeyword] = useState('');
  const [pageSize, setPageSize] = useState(20);
  const conversations = useQuery({
    queryKey: ['tenant', tenantId, 'copilot-conversations', pageSize],
    queryFn: ({ signal }) => listConversations(signal, { page: 1, page_size: pageSize }),
    enabled: tenantId != null,
  });
  const create = useMutation({
    mutationFn: () => createConversation(),
    onSuccess: (row) => {
      void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'copilot-conversations'] });
      setSelectedId(row.id);
      navigate('/chat');
      onNavigate?.();
    },
  });
  const visible = useMemo(() => {
    const list = conversations.data?.items ?? [];
    const q = keyword.trim().toLowerCase();
    return q ? list.filter((item) => item.title.toLowerCase().includes(q)) : list;
  }, [conversations.data?.items, keyword]);
  const loaded = conversations.data?.items.length ?? 0;
  const hasMore =
    (conversations.data?.total ?? 0) > loaded && pageSize < 100 && !keyword.trim();

  const openConversation = (id: number) => {
    setSelectedId(id);
    if (location.pathname !== '/chat') navigate('/chat');
    onNavigate?.();
  };

  const rename = async (id: number, title: string) => {
    await renameConversation(id, title);
    void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'copilot-conversations'] });
  };

  const remove = async (id: number) => {
    await deleteConversation(id);
    if (selectedId === id) setSelectedId(null);
    void query.invalidateQueries({ queryKey: ['tenant', tenantId, 'copilot-conversations'] });
  };

  return (
    <aside
      className={`flex h-full min-h-0 flex-col border-r border-[#E2E8F0] bg-white/90 backdrop-blur-sm transition-[width] duration-200 ${
        collapsed ? 'w-[72px]' : 'w-[260px]'
      } ${narrow ? 'shadow-[8px_0_24px_rgba(15,23,42,0.08)]' : ''}`}
    >
      <div className={`flex items-center gap-3 px-4 py-4 ${collapsed ? 'justify-center' : ''}`}>
        <BrandMark size={36} />
        {collapsed ? null : (
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-[#0F172A]">Neorvion AI</div>
            <div className="truncate text-xs text-[#64748B]">企业智能工作台</div>
          </div>
        )}
      </div>
      <nav className="space-y-1 px-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
                isActive
                  ? 'bg-[#EEF2FF] font-medium text-[#4F46E5]'
                  : 'text-[#475569] hover:bg-[#F8FAFC]'
              } ${collapsed ? 'justify-center px-0' : ''}`
            }
            title={item.label}
          >
            <item.icon size={18} />
            {collapsed ? null : (
              <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                <span className="truncate">{item.label}</span>
                {item.live ? null : (
                  <span className="rounded-full bg-[#F1F5F9] px-2 py-0.5 text-[10px] text-[#64748B]">即将上线</span>
                )}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="mx-4 my-3 h-px bg-[#E2E8F0]" />
      {collapsed ? (
        <div className="flex justify-center px-3">
          <button
            type="button"
            title="新建对话"
            onClick={() => create.mutate()}
            className="copilot-accent-btn h-10 w-10 rounded-xl"
            style={{
              color: '#fff',
              background: 'linear-gradient(135deg, #4F8CFF 0%, #8B5CF6 100%)',
            }}
          >
            <Plus size={18} color="#fff" />
          </button>
        </div>
      ) : (
        <div className="px-3">
          <button
            type="button"
            onClick={() => create.mutate()}
            disabled={create.isPending}
            className="copilot-accent-btn w-full rounded-xl px-3 py-2.5 text-sm font-medium"
            style={{
              color: '#fff',
              background: 'linear-gradient(135deg, #4F8CFF 0%, #8B5CF6 100%)',
            }}
          >
            <Plus size={16} color="#fff" />
            新建对话
          </button>
          <label className="mt-3 flex items-center gap-2 rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] px-3 py-2 text-[#94A3B8]">
            <Search size={14} />
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索会话"
              className="w-full bg-transparent text-sm text-[#0F172A] outline-none placeholder:text-[#94A3B8]"
            />
          </label>
        </div>
      )}
      <div className="copilot-scroll mt-3 min-h-0 flex-1 overflow-y-auto px-2">
        {collapsed ? null : conversations.isPending ? (
          <div className="space-y-2 px-2">
            <Skeleton active paragraph={{ rows: 6 }} title={false} />
          </div>
        ) : visible.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-[#94A3B8]">暂无会话</div>
        ) : (
          visible.map((item) => (
            <div
              key={item.id}
              className={`group mb-1 flex cursor-pointer items-center rounded-xl px-2 py-2 transition ${
                selectedId === item.id ? 'bg-[#EEF2FF] text-[#4F46E5]' : 'text-[#334155] hover:bg-[#F8FAFC]'
              }`}
              onClick={() => openConversation(item.id)}
            >
              <div className="min-w-0 flex-1 truncate px-1 text-sm">{item.title}</div>
              <button
                type="button"
                className="hidden rounded-lg p-1 text-[#94A3B8] hover:bg-white hover:text-[#6366F1] group-hover:block"
                onClick={(event) => {
                  event.stopPropagation();
                  let value = item.title;
                  Modal.confirm({
                    title: '重命名会话',
                    content: <Input defaultValue={value} onChange={(x) => (value = x.target.value)} />,
                    onOk: () => rename(item.id, value),
                  });
                }}
                aria-label="重命名"
              >
                <Pencil size={14} />
              </button>
              <button
                type="button"
                className="hidden rounded-lg p-1 text-[#94A3B8] hover:bg-white hover:text-rose-500 group-hover:block"
                onClick={(event) => {
                  event.stopPropagation();
                  Modal.confirm({ title: '删除会话？', onOk: () => remove(item.id) });
                }}
                aria-label="删除"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
        {collapsed || !hasMore ? null : (
          <button
            type="button"
            className="mb-3 w-full py-2 text-xs text-[#6366F1] hover:underline"
            onClick={() => setPageSize((value) => Math.min(100, value + 20))}
          >
            加载更多
          </button>
        )}
      </div>
      <div className={`border-t border-[#E2E8F0] p-3 ${collapsed ? 'flex justify-center' : ''}`}>
        {collapsed ? null : (
          <div className="mb-2 px-1 text-[11px] leading-5 text-[#94A3B8]">Neorvion AI 工作台 · 仅查询企业授权数据</div>
        )}
        <button
          type="button"
          onClick={onToggle}
          className="flex h-9 w-full items-center justify-center gap-2 rounded-xl text-[#64748B] transition hover:bg-[#F8FAFC]"
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
    </aside>
  );
}
