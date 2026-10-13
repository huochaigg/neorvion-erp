import { BookOutlined, DatabaseOutlined, HomeOutlined } from '@ant-design/icons';
import { Layout, Menu, Tag } from 'antd';
import type { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { isEmbeddedInWujie } from '@/lib/runtime';

const { Sider, Content } = Layout;

interface KnowledgeLayoutProps {
  children: ReactNode;
}

export function KnowledgeLayout({ children }: KnowledgeLayoutProps) {
  const embedded = isEmbeddedInWujie();
  const navigate = useNavigate();
  const location = useLocation();
  const selectedKey = location.pathname.startsWith('/tasks')
    ? '/tasks'
    : location.pathname.startsWith('/bases')
      ? '/bases'
      : '/workbench';

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[#f3f5f8]">
      {embedded ? null : (
        <header className="flex shrink-0 items-center justify-between bg-[#102a43] px-4 py-3">
          <span className="text-sm font-semibold text-white">Neorvion Knowledge · 独立运行</span>
          <Tag color="gold">开发调试</Tag>
        </header>
      )}
      <Layout className="min-h-0 flex-1 overflow-hidden">
        <Sider width={200} className="border-r border-slate-200 bg-white">
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            className="h-full border-none pt-3"
            items={[
              { key: '/workbench', icon: <HomeOutlined />, label: '工作台' },
              { key: '/bases', icon: <BookOutlined />, label: '知识库' },
              { key: '/tasks', icon: <DatabaseOutlined />, label: '处理任务' },
            ]}
            onClick={({ key }) => navigate(key)}
          />
        </Sider>
        <Content className="min-h-0 min-w-0 flex-1 overflow-hidden bg-white px-5 pb-4 pt-4">
          {children}
        </Content>
      </Layout>
    </div>
  );
}
