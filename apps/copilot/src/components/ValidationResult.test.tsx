import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ValidationResult } from './ValidationResult';

describe('ValidationResult', () => {
  it('明确预检通过不代表已创建 ERP 单据', () => {
    const html = renderToStaticMarkup(<ValidationResult value={{
      status: 'VALID', revision: 2, errors: [], warnings: [], missing_fields: [], preview_data: {}, resource_versions: {},
      validated_at: '2026-10-23T00:00:00Z', expires_at: '2026-10-23T00:05:00Z',
    }} />);
    expect(html).toContain('草稿预检通过');
    expect(html).toContain('未创建任何 ERP 单据');
    expect(html).not.toContain('执行成功');
  });

  it('展示待补充字段且不把它当成成功', () => {
    const html = renderToStaticMarkup(<ValidationResult value={{
      status: 'INVALID', revision: 1, errors: [], warnings: [], missing_fields: ['supplier_id'], preview_data: {}, resource_versions: {},
      validated_at: '2026-10-23T00:00:00Z', expires_at: '2026-10-23T00:05:00Z',
    }} />);
    expect(html).toContain('supplier_id');
    expect(html).toContain('草稿预检未通过');
  });
});
