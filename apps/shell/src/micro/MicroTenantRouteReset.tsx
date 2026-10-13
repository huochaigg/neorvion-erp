import { SHELL_EVENTS, isTenantChangedPayload } from '@neorvion/shared';
import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { bus } from 'wujie';
import { hostPathToResetAfterTenantChange, resetUnsafeMicroLastLocations } from '@/micro/reset-tenant-routes';

/** 切租户时修正 Shell 当前 URL 和已保存的子应用路由，不依赖子应用 Host 是否挂载。 */
export function MicroTenantRouteReset() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationRef = useRef(location);
  locationRef.current = location;

  useEffect(() => {
    const onTenantChanged = (...args: unknown[]) => {
      if (!isTenantChangedPayload(args[0])) {
        return;
      }
      resetUnsafeMicroLastLocations();
      const next = hostPathToResetAfterTenantChange(locationRef.current.pathname);
      if (next && next !== locationRef.current.pathname) {
        navigate(next, { replace: true });
      }
    };

    bus.$on(SHELL_EVENTS.tenantChanged, onTenantChanged);
    return () => {
      bus.$off(SHELL_EVENTS.tenantChanged, onTenantChanged);
    };
  }, [navigate]);

  return null;
}
