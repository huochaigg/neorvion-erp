import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { safeHostPathAfterTenantChange, sanitizeMicroHrefAfterTenantChange } from './micro-route';

const knowledge = { name: 'knowledge', basename: '/knowledge', defaultPath: '/bases' };
const erp = { name: 'erp', basename: '/erp', defaultPath: '/dashboard' };

describe('sanitizeMicroHrefAfterTenantChange', () => {
  it('Knowledge 详情页回到列表，列表保留', () => {
    assert.equal(
      sanitizeMicroHrefAfterTenantChange('knowledge', '/knowledge', '/bases', '/knowledge/bases/2'),
      '/knowledge/bases',
    );
    assert.equal(
      sanitizeMicroHrefAfterTenantChange('knowledge', '/knowledge', '/bases', '/knowledge/bases'),
      '/knowledge/bases',
    );
  });

  it('ERP 详情页回到模块列表，工作台保留', () => {
    assert.equal(
      sanitizeMicroHrefAfterTenantChange('erp', '/erp', '/dashboard', '/erp/products/11/edit'),
      '/erp/products/list',
    );
    assert.equal(
      sanitizeMicroHrefAfterTenantChange('erp', '/erp', '/dashboard', '/erp/dashboard'),
      '/erp/dashboard',
    );
  });

  it('空 href 落到默认首页', () => {
    assert.equal(sanitizeMicroHrefAfterTenantChange('knowledge', '/knowledge', '/bases', null), '/knowledge/bases');
  });
});

describe('safeHostPathAfterTenantChange', () => {
  it('当前正在看不安全路由时返回模块首页', () => {
    assert.equal(safeHostPathAfterTenantChange('/knowledge/bases/2', [knowledge, erp]), '/knowledge/bases');
    assert.equal(safeHostPathAfterTenantChange('/erp/orders/9', [knowledge, erp]), '/erp/orders/list');
  });

  it('工作台或列表不改', () => {
    assert.equal(safeHostPathAfterTenantChange('/', [knowledge, erp]), null);
    assert.equal(safeHostPathAfterTenantChange('/knowledge/bases', [knowledge, erp]), null);
    assert.equal(safeHostPathAfterTenantChange('/erp/dashboard', [knowledge, erp]), null);
  });
});
