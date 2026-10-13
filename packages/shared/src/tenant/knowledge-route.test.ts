import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { safeKnowledgePathAfterTenantChange } from './knowledge-route';

describe('safeKnowledgePathAfterTenantChange', () => {
  it('工作台、列表和任务列表可以保留', () => {
    assert.equal(safeKnowledgePathAfterTenantChange('/workbench'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/bases'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/'), null);
    assert.equal(safeKnowledgePathAfterTenantChange('/tasks'), null);
  });

  it('带旧租户资源 ID 的路径回到模块首页', () => {
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2'), '/workbench');
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2/'), '/workbench');
    assert.equal(safeKnowledgePathAfterTenantChange('/bases/2/documents/9'), '/workbench');
    assert.equal(safeKnowledgePathAfterTenantChange('/tasks/18'), '/tasks');
  });
});
