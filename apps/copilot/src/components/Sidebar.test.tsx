import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { Sidebar } from './Sidebar';

function renderSidebar(pathname: string, permissions: string[]) {
  return renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[pathname]}>
        <Sidebar
          collapsed={false}
          narrow={false}
          permissions={permissions}
          onToggle={() => undefined}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Sidebar information architecture', () => {
  it('keeps chat resources local to the assistant page', () => {
    expect(renderSidebar('/chat', ['copilot:use'])).toContain('新建对话');
    expect(renderSidebar('/tasks', ['copilot:use'])).not.toContain('新建对话');
  });

  it('shows protected modules only with their catalog permissions', () => {
    const ordinary = renderSidebar('/chat', ['copilot:use']);
    expect(ordinary).not.toContain('业务洞察');
    expect(ordinary).not.toContain('AI 管理中心');

    const administrator = renderSidebar('/manage', [
      'copilot:use',
      'copilot:insight:read',
      'copilot:evaluation:read',
    ]);
    expect(administrator).toContain('业务洞察');
    expect(administrator).toContain('AI 管理中心');
  });
});
