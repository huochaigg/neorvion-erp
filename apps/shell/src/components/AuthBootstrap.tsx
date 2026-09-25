import { currentUserQueryKey } from '@neorvion/shared';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { refreshSession } from '@/api/client';
import { useAuthStore } from '@/stores/auth-store';

interface AuthBootstrapProps {
  children: ReactNode;
}

export function AuthBootstrap({ children }: AuthBootstrapProps) {
  const hydrated = useAuthStore((state) => state.hydrated);
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const setHydrated = useAuthStore((state) => state.setHydrated);
  const queryClient = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const tokens = await refreshSession();
        if (!cancelled) {
          setAccessToken(tokens?.access_token ?? null);
        }
      } catch {
        if (!cancelled) {
          setAccessToken(null);
          queryClient.removeQueries({ queryKey: currentUserQueryKey() });
        }
      } finally {
        if (!cancelled) {
          setHydrated(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [queryClient, setAccessToken, setHydrated]);

  if (!hydrated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f3f5f8] text-sm text-slate-500">
        正在恢复登录状态…
      </div>
    );
  }

  return children;
}
