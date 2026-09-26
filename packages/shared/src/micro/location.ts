import type { MicroLocationPayload } from '../types/bridge';

export function composePath(pathname: string, search = '', hash = ''): string {
  return `${pathname}${search}${hash}`;
}

export function childPathFromHost(hostPathname: string, basename: string, defaultPath: string): string {
  if (hostPathname === basename || hostPathname === `${basename}/`) {
    return defaultPath;
  }
  if (hostPathname.startsWith(`${basename}/`)) {
    const child = hostPathname.slice(basename.length);
    return child.startsWith('/') ? child : `/${child}`;
  }
  return defaultPath;
}

export function hostPathFromChild(basename: string, childPathname: string): string {
  const child = childPathname.startsWith('/') ? childPathname : `/${childPathname}`;
  if (child === basename || child.startsWith(`${basename}/`)) {
    return child;
  }
  if (child === '/') {
    return basename;
  }
  return `${basename}${child}`;
}

export function isMicroLocationPayload(value: unknown): value is MicroLocationPayload {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const payload = value as Partial<MicroLocationPayload>;
  return typeof payload.name === 'string' && typeof payload.pathname === 'string';
}
