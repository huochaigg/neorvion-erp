import { currentUserQueryKey } from '@neorvion/shared';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { restoreSession } from '@/api/client';
import { useAuthStore } from '@/stores/auth-store';

interface AuthBootstrapProps {
  children: ReactNode;
}

export function AuthBootstrap({ children }: AuthBootstrapProps) {
  const status = useAuthStore((state) => state.status);
  const markAuthenticated = useAuthStore((state) => state.markAuthenticated);
  const markUnauthenticated = useAuthStore((state) => state.markUnauthenticated);
  const queryClient = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const existing = useAuthStore.getState().accessToken;
      if (existing) {
        if (!cancelled) {
          markAuthenticated(existing);
        }
        return;
      }
      try {
        const token = await restoreSession();
        if (cancelled) {
          return;
        }
        if (token) {
          return;
        }
        queryClient.removeQueries({ queryKey: currentUserQueryKey() });
        if (useAuthStore.getState().status === 'initializing') {
          markUnauthenticated();
        }
      } catch {
        if (!cancelled && useAuthStore.getState().status === 'initializing') {
          markUnauthenticated();
          queryClient.removeQueries({ queryKey: currentUserQueryKey() });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [markAuthenticated, markUnauthenticated, queryClient]);

  if (status === 'initializing') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f3f5f8] text-sm text-slate-500">
        正在恢复登录状态…
      </div>
    );
  }

  return children;
}
