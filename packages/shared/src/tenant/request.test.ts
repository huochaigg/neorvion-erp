import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { decideTenantHeader, shouldAttachTenantHeader } from './request';

describe('shouldAttachTenantHeader', () => {
  it('认证与租户发现接口不带 X-Tenant-ID', () => {
    assert.equal(shouldAttachTenantHeader('GET', '/api/crypto/public-key'), false);
    assert.equal(shouldAttachTenantHeader('POST', '/api/v1/auth/register'), false);
    assert.equal(shouldAttachTenantHeader('POST', '/api/v1/auth/login'), false);
    assert.equal(shouldAttachTenantHeader('POST', '/api/v1/auth/refresh'), false);
    assert.equal(shouldAttachTenantHeader('POST', '/api/v1/auth/logout'), false);
    assert.equal(shouldAttachTenantHeader('GET', '/api/v1/auth/me'), false);
    assert.equal(shouldAttachTenantHeader('POST', '/api/v1/tenants'), false);
    assert.equal(shouldAttachTenantHeader('GET', '/api/v1/tenants'), false);
    assert.equal(shouldAttachTenantHeader('GET', '/api/v1/health'), false);
  });

  it('不用字符串包含误伤 /tenants/current 或带尾斜杠的列表', () => {
    assert.equal(shouldAttachTenantHeader('GET', '/api/v1/tenants/current'), true);
    assert.equal(shouldAttachTenantHeader('GET', '/api/v1/tenants/'), false);
    assert.equal(shouldAttachTenantHeader('GET', '/api/v1/tenants/1001'), true);
    assert.equal(shouldAttachTenantHeader('POST', '/api/v1/tenants/1001/members'), true);
  });
});

describe('decideTenantHeader', () => {
  it('在请求发起时绑定当前租户，切换中拒绝业务请求', () => {
    assert.deepEqual(
      decideTenantHeader({
        method: 'GET',
        url: '/api/v1/tenants/current',
        currentTenantId: 1001,
        isSwitching: false,
      }),
      { action: 'attach', tenantId: 1001 },
    );
    assert.deepEqual(
      decideTenantHeader({
        method: 'GET',
        url: '/api/v1/tenants/current',
        currentTenantId: 1001,
        isSwitching: true,
      }),
      { action: 'reject', reason: 'switching' },
    );
    assert.deepEqual(
      decideTenantHeader({
        method: 'GET',
        url: '/api/v1/tenants',
        currentTenantId: 1001,
        isSwitching: true,
      }),
      { action: 'skip' },
    );
    assert.deepEqual(
      decideTenantHeader({
        method: 'POST',
        url: '/api/v1/tenants',
        currentTenantId: null,
        isSwitching: false,
      }),
      { action: 'skip' },
    );
  });
});
