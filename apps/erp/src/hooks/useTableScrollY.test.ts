import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { measureTableScrollY } from './useTableScrollY';

describe('useTableScrollY', () => {
  it('按容器高度减去表头和分页，得到 Table body 的 scroll.y', () => {
    const container = {
      clientHeight: 500,
      querySelector: (selector: string) => {
        if (selector === '.ant-table-header' || selector === '.ant-table-thead') {
          return { getBoundingClientRect: () => ({ height: 40 }) };
        }
        if (selector === '.ant-table-pagination') {
          return { getBoundingClientRect: () => ({ height: 56 }) };
        }
        return null;
      },
    } as unknown as HTMLElement;
    assert.equal(measureTableScrollY(container, true), 396);
    assert.equal(measureTableScrollY(container, false), 452);
  });

  it('容器过矮时仍保留最小 body 高度，避免 y=0', () => {
    const tiny = {
      clientHeight: 50,
      querySelector: () => null,
    } as unknown as HTMLElement;
    assert.equal(measureTableScrollY(tiny, true), 160);
  });
});
