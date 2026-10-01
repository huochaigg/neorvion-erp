import { SESSION_EXPIRED_MESSAGE } from '@neorvion/shared';
import { warnSessionExpired } from '@/lib/antd-app';
import { getRegisteredQueryClient } from '@/lib/query-client';
import { queueAuthNotice } from '@/lib/session-notice';
import { destroyAllMicroApps } from '@/micro/lifecycle';
import { useAuthStore } from '@/stores/auth-store';
import { useTenantStore } from '@/stores/tenant-store';

/** Refresh 失败后清会话。RequireAuth 会把用户送到登录页。 */
export function endSessionDueToExpiry(message = SESSION_EXPIRED_MESSAGE) {
  if (useAuthStore.getState().status !== 'authenticated') {
    return;
  }
  queueAuthNotice(message);
  useAuthStore.getState().markUnauthenticated();
  useTenantStore.getState().reset();
  getRegisteredQueryClient()?.clear();
  destroyAllMicroApps();
  warnSessionExpired(message);
}
