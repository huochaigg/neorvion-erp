import { SHELL_ROUTES } from '@neorvion/shared';
import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth-store';

interface RequireAuthProps {
  children: ReactNode;
}

export function RequireAuth({ children }: RequireAuthProps) {
  const status = useAuthStore((state) => state.status);
  const location = useLocation();

  if (status === 'initializing') {
    return null;
  }
  if (status !== 'authenticated') {
    return <Navigate to={SHELL_ROUTES.login} replace state={{ from: location }} />;
  }

  return children;
}
