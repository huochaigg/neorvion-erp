import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { IntentStatusCard } from './IntentStatusCard';

describe('IntentStatusCard', () => {
  it('shows a compact intent summary without raw JSON', () => {
    const html = renderToStaticMarkup(
      <IntentStatusCard
        status={{ status_text: '已识别：库存查询', decision: 'CLEAR', intents: ['inventory.query'] }}
      />,
    );
    expect(html).toContain('已识别：库存查询');
    expect(html).not.toContain('inventory.query');
  });

  it('offers cancel only while pending', () => {
    const html = renderToStaticMarkup(
      <IntentStatusCard
        status={{ status_text: '需要补充：供应商', decision: 'INSUFFICIENT', pending: true, missing_slots: ['supplier'] }}
        onCancel={() => undefined}
      />,
    );
    expect(html).toContain('取消本次补充');
    expect(html).toContain('待补：supplier');
  });
});
