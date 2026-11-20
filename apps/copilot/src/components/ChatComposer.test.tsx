import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ChatComposer } from './ChatComposer';

const inventorySkill = {
  skill_id: 1,
  version_id: 11,
  skill_key: 'inventory-analysis',
  name: '库存风险分析',
  description: '只读库存分析',
  version: 2,
  category: 'inventory',
  required_permissions: ['inventory:read'],
};

function renderComposer(
  skillMode: 'AUTO' | 'MANUAL' | 'NONE',
  extra?: Partial<Parameters<typeof ChatComposer>[0]>,
) {
  return renderToStaticMarkup(
    <ChatComposer
      value="分析库存"
      running={false}
      placeholder="输入问题"
      onChange={vi.fn()}
      onSend={vi.fn()}
      onStop={vi.fn()}
      skillMode={skillMode}
      skillKey="inventory-analysis"
      autoAvailable
      onSkillModeChange={vi.fn()}
      onSkillKeyChange={vi.fn()}
      skills={[inventorySkill]}
      {...extra}
    />,
  );
}

describe('ChatComposer Skill Picker', () => {
  it('shows the selected skill name instead of AUTO/MANUAL/NONE jargon', () => {
    const html = renderComposer('MANUAL');
    expect(html).toContain('库存风险分析');
    expect(html).toContain('只读库存分析');
    expect(html).not.toContain('>自动<');
    expect(html).not.toContain('>手动<');
    expect(html).not.toContain('>不使用<');
  });

  it('labels auto and none modes in plain language', () => {
    expect(renderComposer('AUTO')).toContain('按问题匹配');
    expect(renderComposer('AUTO')).toContain('系统根据问题选择已启用 Skill');
    expect(renderComposer('NONE')).toContain('普通对话');
    expect(renderComposer('NONE')).toContain('不调用 Skill，仍可使用已授权工具');
  });

  it('explains empty catalog instead of hiding manual selection', () => {
    const html = renderComposer('NONE', { skills: [] });
    expect(html).toContain('普通对话');
    expect(html).not.toContain('库存风险分析');
  });
});
