import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ChatComposer } from './ChatComposer';

describe('ChatComposer Skill Picker', () => {
  it('renders AUTO MANUAL NONE and only authorized runnable skills', () => {
    const html = renderToStaticMarkup(
      <ChatComposer
        value="分析库存"
        running={false}
        placeholder="输入问题"
        onChange={vi.fn()}
        onSend={vi.fn()}
        onStop={vi.fn()}
        skillMode="MANUAL"
        skillKey="inventory-analysis"
        autoAvailable
        onSkillModeChange={vi.fn()}
        onSkillKeyChange={vi.fn()}
        skills={[{
          skill_id: 1,
          version_id: 11,
          skill_key: 'inventory-analysis',
          name: '库存风险分析',
          description: '只读库存分析',
          version: 2,
          category: 'inventory',
          required_permissions: ['inventory:read'],
        }]}
      />,
    );
    expect(html).toContain('自动');
    expect(html).toContain('手动');
    expect(html).toContain('不使用');
    expect(html).toContain('库存风险分析');
    expect(html).toContain('只读库存分析');
  });
});
