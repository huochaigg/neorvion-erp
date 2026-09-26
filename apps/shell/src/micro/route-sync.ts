import { bus } from 'wujie';
import {
  MICRO_EVENTS,
  childPathFromHost,
  composePath,
  hostPathFromChild,
  isMicroLocationPayload,
  type MicroLocationPayload,
} from '@neorvion/shared';
import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { stripMicroSyncParam, type MicroAppDefinition } from '@/micro/apps';
import { setLastMicroHref } from '@/micro/last-location';

export function emitHostNavigate(
  app: MicroAppDefinition,
  location: { pathname: string; search: string; hash: string },
) {
  const payload: MicroLocationPayload = {
    name: app.name,
    pathname: childPathFromHost(location.pathname, app.basename, app.defaultPath),
    search: stripMicroSyncParam(location.search, app.name),
    hash: location.hash,
    action: 'replace',
  };
  bus.$emit(MICRO_EVENTS.hostNavigate, payload);
}

export function consumeLegacyWujieSyncQuery(
  app: MicroAppDefinition,
  location: { pathname: string; search: string; hash: string },
): string | null {
  const params = new URLSearchParams(location.search);
  const raw = params.get(app.name);
  if (!raw) {
    return null;
  }
  params.delete(app.name);
  let child = decodeURIComponent(raw);
  child = child.replaceAll(`{${app.name}}`, app.basename);
  if (!child.startsWith('/')) {
    child = `/${child}`;
  }
  const pathname = hostPathFromChild(app.basename, child);
  const rest = params.toString();
  return composePath(pathname, rest ? `?${rest}` : '', location.hash);
}

export function useMicroHostRouteSync(app: MicroAppDefinition) {
  const location = useLocation();
  const navigate = useNavigate();
  const locationRef = useRef(location);
  const syncingFromChildRef = useRef(false);
  locationRef.current = location;

  useEffect(() => {
    const onChildLocation = (...args: unknown[]) => {
      const payload = args[0];
      if (!isMicroLocationPayload(payload) || payload.name !== app.name) {
        return;
      }
      const next = composePath(
        hostPathFromChild(app.basename, payload.pathname),
        payload.search ?? '',
        payload.hash ?? '',
      );
      setLastMicroHref(app.name, next);
      const current = composePath(
        locationRef.current.pathname,
        locationRef.current.search,
        locationRef.current.hash,
      );
      if (current === next) {
        return;
      }
      syncingFromChildRef.current = true;
      navigate(next, { replace: payload.action === 'replace' });
    };

    bus.$on(MICRO_EVENTS.childLocation, onChildLocation);
    return () => {
      bus.$off(MICRO_EVENTS.childLocation, onChildLocation);
    };
  }, [app.basename, app.name, navigate]);

  useEffect(() => {
    const href = composePath(location.pathname, location.search, location.hash);
    setLastMicroHref(app.name, href);
    if (syncingFromChildRef.current) {
      syncingFromChildRef.current = false;
      return;
    }
    emitHostNavigate(app, location);
  }, [app, location]);
}
