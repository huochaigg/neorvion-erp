import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { safeKnowledgePathAfterTenantChange } from './knowledge-route';

describe('safeKnowledgePathAfterTenantChange', () => {
  it('工作台、列表和任务列表可以保留', () => {
    assert.equal(safeKnowledgePathAfterTenantChange('/workbench'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/bases'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/tasks'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/search'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/chat'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/retrieval-test'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/models'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/datasets'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/experiments'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/experiments/compare'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/stats'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/recycle'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/api-keys'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/audit'), null);
  });

  it('带旧租户资源 ID 的路径回到模块首页', () => {
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2'), '/workbench');
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2/'), '/workbench');
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2/documents/9'), '/workbench');
    assert.equal(safeKnowledgePathAfterTenantChange('/chat/18'), '/chat');
    assert.equal(safeKnowledgePathAfterTenantChange('/tasks/18'), '/tasks');
    assert.equal(safeKnowledgePathAfterTenantChange('/datasets/9'), '/datasets');
    assert.equal(safeKnowledgePathAfterTenantChange('/experiments/4'), '/experiments');
  });
});
