import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { safeKnowledgePathAfterTenantChange } from './knowledge-route';

describe('safeKnowledgePathAfterTenantChange', () => {
  it('列表可以保留', () => {
    assert.equal(safeKnowledgePathAfterTenantChange('/bases'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/'), null);
  });

  it('带旧租户知识库 ID 的路径回到列表', () => {
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2'), '/bases');
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2/'), '/bases');
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2/edit'), '/bases');
  });
});
