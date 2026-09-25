import { SHELL_ROUTES } from '@neorvion/shared';
import { Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth-store';

interface GuestOnlyProps {
  children: ReactNode;
}

export function GuestOnly({ children }: GuestOnlyProps) {
  const status = useAuthStore((state) => state.status);
  if (status === 'initializing') {
    return null;
  }
  if (status === 'authenticated') {
    return <Navigate to={SHELL_ROUTES.home} replace />;
  }
  return children;
}
