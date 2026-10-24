import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ExecutionStatus } from './ExecutionStatus';

describe('ExecutionStatus', () => {
  it('UNKNOWN 明确提示正在对账而不是失败重试', () => {
    const html = renderToStaticMarkup(<ExecutionStatus value="UNKNOWN" />);
    expect(html).toContain('正在确认 ERP 实际结果');
    expect(html).not.toContain('执行失败');
  });
});
