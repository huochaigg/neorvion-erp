import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/api/proposals', () => ({
  getCurrentIdentity: vi.fn(),
  cancelProposal: vi.fn(),
  updateProposal: vi.fn(),
  validateProposal: vi.fn(),
}));
vi.mock('./ProposalDetail', () => ({ ProposalDetail: () => null }));
import { ProposalCard } from './ProposalCard';
import { useCopilotStore } from '@/store';

describe('ProposalCard', () => {
  it('只提供草稿操作，不渲染正式执行按钮', () => {
    useCopilotStore.setState({ tenantId: 7 });
    const client = new QueryClient();
    client.setQueryData(['tenant', 7, 'copilot-current-identity'], {
      permissions: ['purchase:create'],
    });
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <ProposalCard value={{
          id: 1, conversation_id: 2, source_message_id: 3,
          action_type: 'PURCHASE_ORDER_CREATE', schema_version: 1, status: 'READY',
          current_revision: 2, payload: {}, editable_fields: [], validation: null,
          expires_at: '2026-10-24T00:00:00Z', created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z',
        }} onChanged={() => undefined} />
      </QueryClientProvider>,
    );
    expect(html).toContain('采购草稿');
    expect(html).toContain('当前权限不允许操作此草稿');
    expect(html).not.toContain('确认执行');
    expect(html).not.toContain('创建采购单成功');
  });
});
