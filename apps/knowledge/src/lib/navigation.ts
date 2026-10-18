import type { NavigateFunction } from 'react-router-dom';

export function goBackOr(navigate: NavigateFunction, fallback: string) {
  const state = window.history.state as { idx?: number } | null;
  if (typeof state?.idx === 'number' && state.idx > 0) {
    navigate(-1);
    return;
  }
  if (document.referrer) {
    try {
      const referrer = new URL(document.referrer);
      if (referrer.origin === window.location.origin && referrer.href !== window.location.href) {
        navigate(-1);
        return;
      }
    } catch {
      /* 直接打开或微前端无可用 referrer 时走安全入口 */
    }
  }
  navigate(fallback);
}
