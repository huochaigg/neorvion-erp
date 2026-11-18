import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { SkillRun } from '@/api/ecosystem';
import { RunDetail } from './EcosystemManagementPage';

describe('Skill run detail', () => {
  it('renders structured result, tool summary, evidence and safe error', () => {
    const run: SkillRun = {
      id: 1,
      skill_id: 2,
      skill_version: 3,
      user_id: 4,
      idempotency_key: 'skill-run-0001',
      status: 'FAILED',
      input_snapshot: { order_id: 71 },
      output_snapshot: {
        result: { summary: '订单审查完成' },
        tool_calls: [{ name: 'get_sales_order', status: 'SUCCEEDED' }],
        evidence: [{ citation_id: 'E1', source_type: 'ERP' }],
      },
      safe_error: '输出 Schema 校验失败',
      started_at: '2026-11-09T10:00:00+08:00',
      finished_at: '2026-11-09T10:00:01+08:00',
      created_at: '2026-11-09T10:00:00+08:00',
    };
    const html = renderToStaticMarkup(<RunDetail run={run} />);
    expect(html).toContain('结构化结果');
    expect(html).toContain('get_sales_order');
    expect(html).toContain('Evidence');
    expect(html).toContain('输出 Schema 校验失败');
  });
});
