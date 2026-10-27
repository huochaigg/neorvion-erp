import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import InsightCenterPage from './InsightCenterPage';

describe('InsightCenterPage', () => {
  it('renders honest empty states and the deterministic safety boundary', () => {
    const client = new QueryClient();
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <InsightCenterPage />
      </QueryClientProvider>,
    );
    expect(html).toContain('主动洞察中心');
    expect(html).toContain('不会自动修改 ERP');
    expect(html).toContain('尚无业务预警');
    expect(html).not.toContain('AI 分析成功率 100%');
  });
});
