import type { ShellToErpProps } from '@neorvion/shared';

export function isEmbeddedInWujie() {
  return Boolean(window.__POWERED_BY_WUJIE__);
}

export function getShellProps(): ShellToErpProps {
  return (
    window.$wujie?.props ?? {
      token: null,
      tenantId: null,
      user: null,
    }
  );
}

export function getPopupContainer(node?: HTMLElement) {
  if (node) {
    const overlayRoot = node.closest('#root');
    if (overlayRoot instanceof HTMLElement) {
      return overlayRoot;
    }
  }
  return document.getElementById('root') ?? document.body;
}
