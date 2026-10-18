import { describe, expect, it } from 'vitest';
import { snapshotParam } from './snapshotParam';

describe('snapshotParam', () => {
  it('marks missing keys as unrecorded', () => {
    expect(snapshotParam({ top_k: 8 }, 'vector_k')).toBe('未记录');
    expect(snapshotParam(undefined, 'top_k')).toBe('未记录');
  });

  it('does not invent defaults for explicit null', () => {
    expect(snapshotParam({ vector_k: null }, 'vector_k')).toBe('未指定');
  });

  it('renders recorded values as-is', () => {
    expect(snapshotParam({ rrf_k: 60, rerank: false }, 'rrf_k')).toBe('60');
    expect(snapshotParam({ rerank: false }, 'rerank')).toBe('关');
    expect(snapshotParam({ rerank: true }, 'rerank')).toBe('开');
  });
});
