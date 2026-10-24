import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import EvaluationCenterPage from './EvaluationCenterPage';

describe('EvaluationCenterPage', () => {
  it('renders an honest empty evaluation center without fabricated metrics', () => {
    const client = new QueryClient();
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <EvaluationCenterPage />
      </QueryClientProvider>,
    );
    expect(html).toContain('Agent Evaluation Center');
    expect(html).toContain('尚无评测数据集');
    expect(html).not.toContain('100%');
  });
});
