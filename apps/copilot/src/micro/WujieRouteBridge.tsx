import { COPILOT_APP_NAME, MICRO_EVENTS, composePath, isMicroLocationPayload } from '@neorvion/shared';
import { useEffect, useLayoutEffect, useRef } from 'react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import { isEmbeddedInWujie } from '@/runtime';

export function WujieRouteBridge() {
  const location = useLocation();
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const locationRef = useRef(location);
  const applyingHostRef = useRef(false);

  useLayoutEffect(() => {
    locationRef.current = location;
  }, [location]);

  useLayoutEffect(() => {
    if (!isEmbeddedInWujie()) {
      return undefined;
    }
    const eventBus = window.$wujie?.bus;
    if (!eventBus) {
      return undefined;
    }

    const onHostNavigate = (...args: unknown[]) => {
      const payload = args[0];
      if (!isMicroLocationPayload(payload) || payload.name !== COPILOT_APP_NAME) {
        return;
      }
      const target = composePath(payload.pathname, payload.search ?? '', payload.hash ?? '');
      const current = composePath(
        locationRef.current.pathname,
        locationRef.current.search,
        locationRef.current.hash,
      );
      if (target === current) {
        return;
      }
      applyingHostRef.current = true;
      navigate(
        {
          pathname: payload.pathname,
          search: payload.search ?? '',
          hash: payload.hash ?? '',
        },
        { replace: payload.action !== 'push' },
      );
    };

    eventBus.$on(MICRO_EVENTS.hostNavigate, onHostNavigate);
    return () => {
      eventBus.$off(MICRO_EVENTS.hostNavigate, onHostNavigate);
    };
  }, [navigate]);

  useEffect(() => {
    if (!isEmbeddedInWujie()) {
      return;
    }
    if (applyingHostRef.current) {
      applyingHostRef.current = false;
      return;
    }
    window.$wujie?.bus?.$emit(MICRO_EVENTS.childLocation, {
      name: COPILOT_APP_NAME,
      pathname: location.pathname,
      search: location.search,
      hash: location.hash,
      action: navigationType === 'PUSH' ? 'push' : 'replace',
    });
  }, [location, navigationType]);

  return null;
}
