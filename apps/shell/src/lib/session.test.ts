import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import { consumePendingAuthNotice, queueAuthNotice } from './session-notice';

describe('auth session notice', () => {
  it('登录过期提示只消费一次', () => {
    queueAuthNotice('登录已过期，请重新登录');
    assert.equal(consumePendingAuthNotice(), '登录已过期，请重新登录');
    assert.equal(consumePendingAuthNotice(), null);
  });
});
