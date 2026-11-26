import { AxiosError } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from './client';

const { state } = vi.hoisted(() => ({
  state: {
    token: 'old',
    tenantId: 1,
    epoch: 0,
    refreshSession: vi.fn(async () => 'new'),
    expireSession: vi.fn(),
  },
}));

vi.mock('@/lib/runtime', () => ({
  getShellProps: () => ({
    token: state.token,
    user: { id: 1 },
    refreshSession: state.refreshSession,
    expireSession: state.expireSession,
    sessionVersion: () => 0,
  }),
}));
vi.mock('@/stores/tenant-runtime', () => ({
  useErpTenantStore: {
    getState: () => ({ currentTenantId: state.tenantId, epoch: state.epoch }),
  },
}));

describe('ERP IAM recovery', () => {
  beforeEach(() => {
    state.token = 'old';
    state.tenantId = 1;
    state.epoch = 0;
    state.refreshSession = vi.fn(async () => {
      state.token = 'new';
      return 'new';
    });
    state.expireSession.mockClear();
  });

  it('retries an expired request once under the same tenant and does not refresh on 403', async () => {
    const previous = apiClient.defaults.adapter;
    const attempts: string[] = [];
    apiClient.defaults.adapter = async (config) => {
      attempts.push(String(config.headers.Authorization));
      const status = attempts.length === 1 ? 401 : 200;
      const response = {
        config,
        status,
        statusText: '',
        headers: {},
        data: { code: status === 401 ? 40103 : 0 },
      };
      if (status === 401)
        throw new AxiosError('expired', 'ERR_BAD_RESPONSE', config, undefined, response);
      return response;
    };
    try {
      await apiClient.get('/api/v1/orders');
      expect(attempts).toEqual(['Bearer old', 'Bearer new']);
      expect(state.refreshSession).toHaveBeenCalledTimes(1);
      state.refreshSession.mockClear();
      apiClient.defaults.adapter = async (config) => {
        throw new AxiosError('forbidden', 'ERR_BAD_RESPONSE', config, undefined, {
          config,
          status: 403,
          statusText: '',
          headers: {},
          data: { code: 40301 },
        });
      };
      await expect(apiClient.get('/api/v1/orders')).rejects.toMatchObject({ status: 403 });
      expect(state.refreshSession).not.toHaveBeenCalled();
    } finally {
      apiClient.defaults.adapter = previous;
    }
  });
});
