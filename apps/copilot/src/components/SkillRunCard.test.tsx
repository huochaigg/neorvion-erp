import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SkillRunCard } from './SkillRunCard';

describe('SkillRunCard', () => {
  it('renders selected version, status and progressively loaded references', () => {
    const html = renderToStaticMarkup(<SkillRunCard runs={[{
      id: 142,
      skill_id: 14,
      skill_key: 'inventory-analysis',
      skill_name: 'inventory-analysis',
      skill_version: 2,
      status: 'SUCCEEDED',
      selection_method: 'DETERMINISTIC_RULE',
      loaded_resources: ['references/inventory-rules.md'],
      safe_error: null,
    }]} />);
    expect(html).toContain('inventory-analysis');
    expect(html).toContain('SkillRun #142');
    expect(html).toContain('references/inventory-rules.md');
    expect(html).toContain('SUCCEEDED');
  });
});
