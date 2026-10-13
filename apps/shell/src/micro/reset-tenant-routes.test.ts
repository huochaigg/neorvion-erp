import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, it } from 'vitest';
import { ERP_APP_NAME, KNOWLEDGE_APP_NAME } from '@neorvion/shared';
import { clearAllLastMicroHrefs, getLastMicroHref, setLastMicroHref } from '@/micro/last-location';
import { hostPathToResetAfterTenantChange, resetUnsafeMicroLastLocations } from './reset-tenant-routes';

function installSessionStorage() {
  const memory = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return memory.size;
    },
    clear() {
      memory.clear();
    },
    getItem(key) {
      return memory.has(key) ? memory.get(key)! : null;
    },
    key(index) {
      return [...memory.keys()][index] ?? null;
    },
    removeItem(key) {
      memory.delete(key);
    },
    setItem(key, value) {
      memory.set(key, value);
    },
  };
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: storage,
  });
}

describe('resetUnsafeMicroLastLocations', () => {
  beforeEach(() => {
    installSessionStorage();
    clearAllLastMicroHrefs();
  });

  afterEach(() => {
    clearAllLastMicroHrefs();
  });

  it('把未激活子应用保存的详情页换成模块首页，列表和工作台保留', () => {
    setLastMicroHref(KNOWLEDGE_APP_NAME, '/knowledge/bases/2');
    setLastMicroHref(ERP_APP_NAME, '/erp/products/11/edit');
    resetUnsafeMicroLastLocations();
    assert.equal(getLastMicroHref(KNOWLEDGE_APP_NAME), '/knowledge/workbench');
    assert.equal(getLastMicroHref(ERP_APP_NAME), '/erp/products/list');
  });

  it('从未进入过的子应用不会被写成默认首页', () => {
    setLastMicroHref(KNOWLEDGE_APP_NAME, '/knowledge/bases/2');
    resetUnsafeMicroLastLocations();
    assert.equal(getLastMicroHref(KNOWLEDGE_APP_NAME), '/knowledge/workbench');
    assert.equal(getLastMicroHref(ERP_APP_NAME), null);
  });

  it('列表与工作台不被改写', () => {
    setLastMicroHref(KNOWLEDGE_APP_NAME, '/knowledge/bases');
    setLastMicroHref(ERP_APP_NAME, '/erp/dashboard');
    resetUnsafeMicroLastLocations();
    assert.equal(getLastMicroHref(KNOWLEDGE_APP_NAME), '/knowledge/bases');
    assert.equal(getLastMicroHref(ERP_APP_NAME), '/erp/dashboard');
  });
});

describe('hostPathToResetAfterTenantChange', () => {
  it('当前正在看旧租户详情时回到模块首页', () => {
    assert.equal(hostPathToResetAfterTenantChange('/knowledge/bases/2'), '/knowledge/workbench');
    assert.equal(hostPathToResetAfterTenantChange('/knowledge/chat/18'), '/knowledge/chat');
    assert.equal(hostPathToResetAfterTenantChange('/erp/orders/9'), '/erp/orders/list');
  });

  it('工作台、列表和 Shell 自身路由不改', () => {
    assert.equal(hostPathToResetAfterTenantChange('/'), null);
    assert.equal(hostPathToResetAfterTenantChange('/workspaces'), null);
    assert.equal(hostPathToResetAfterTenantChange('/knowledge/bases'), null);
    assert.equal(hostPathToResetAfterTenantChange('/erp/dashboard'), null);
  });
});
