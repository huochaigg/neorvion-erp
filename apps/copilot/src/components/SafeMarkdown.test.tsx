import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { parseMarkdownBlocks, SafeMarkdown } from './SafeMarkdown';

describe('SafeMarkdown', () => {
  it('流式输出 # 后接空格时不会死循环（用户崩溃复现）', () => {
    const started = Date.now();
    let draft = '';
    for (const delta of ['#', ' ', '商品', '查询', '结果']) {
      draft += delta;
      const blocks = parseMarkdownBlocks(draft);
      expect(blocks.length).toBeGreaterThan(0);
      renderToStaticMarkup(<SafeMarkdown text={draft} />);
    }
    expect(parseMarkdownBlocks('#')).toEqual([{ type: 'paragraph', text: '#' }]);
    expect(parseMarkdownBlocks('# ')).toEqual([{ type: 'heading', level: 1, text: '' }]);
    expect(parseMarkdownBlocks('## ')).toEqual([{ type: 'heading', level: 2, text: '' }]);
    expect(parseMarkdownBlocks('# 商品查询结果')).toEqual([{ type: 'heading', level: 1, text: '商品查询结果' }]);
    expect(parseMarkdownBlocks('上文\n# ')).toEqual([
      { type: 'paragraph', text: '上文' },
      { type: 'heading', level: 1, text: '' },
    ]);
    expect(Date.now() - started).toBeLessThan(200);
  });

  it('不使用 HTML 注入', () => {
    const html = renderToStaticMarkup(<SafeMarkdown text="<img src=x onerror=alert(1)>" />);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
  });

  it('历史消息全量重解析成本随轮次上升，隔离直播消息后显著下降', () => {
    const table = [
      '# 库存分析',
      '',
      '| SKU | 仓库 | 数量 | 覆盖天数 |',
      '| --- | --- | --- | --- |',
      ...Array.from({ length: 24 }, (_, index) => `| SKU-${index} | W1 | ${index * 3} | **${index + 2}** |`),
      '',
      '```sql',
      'select sku_code, on_hand from inventory;',
      '```',
    ].join('\n');
    const history = 16;
    const tokens = 60;
    const fullStarted = performance.now();
    for (let token = 0; token < tokens; token += 1) {
      for (let item = 0; item < history; item += 1) parseMarkdownBlocks(table);
      parseMarkdownBlocks(`${table}\n追加 ${token}`);
    }
    const fullMs = performance.now() - fullStarted;
    const isolatedStarted = performance.now();
    for (let item = 0; item < history; item += 1) parseMarkdownBlocks(table);
    for (let token = 0; token < tokens; token += 1) parseMarkdownBlocks(`${table}\n追加 ${token}`);
    const isolatedMs = performance.now() - isolatedStarted;
    console.info(
      `[copilot-chat-perf] full=${fullMs.toFixed(2)}ms isolated=${isolatedMs.toFixed(2)}ms ratio=${(fullMs / Math.max(isolatedMs, 0.01)).toFixed(2)}`,
    );
    expect(fullMs).toBeGreaterThan(isolatedMs * 4);
    expect(parseMarkdownBlocks(table).some((block) => block.type === 'table')).toBe(true);
  });
});
