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
  const shadowRoot = window.$wujie?.shadowRoot;
  if (shadowRoot) {
    const shadowAppRoot = shadowRoot.querySelector('#root');
    if (shadowAppRoot instanceof HTMLElement) {
      return shadowAppRoot;
    }
    const shadowBody = shadowRoot.querySelector('body');
    if (shadowBody instanceof HTMLElement) {
      return shadowBody;
    }
  }
  return document.getElementById('root') ?? document.body;
}
