import { currentUserQueryKey, SHELL_ROUTES, type UserProfile } from '@neorvion/shared';
import { useQuery } from '@tanstack/react-query';
import { Spin } from 'antd';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { fetchCurrentUser } from '@/api/auth';
import { useAuthStore } from '@/stores/auth-store';

export function RequirePasswordChange() {
  const location = useLocation();
  const accessToken = useAuthStore((state) => state.accessToken);
  const { data: user, isLoading } = useQuery<UserProfile>({
    queryKey: currentUserQueryKey(),
    queryFn: fetchCurrentUser,
    enabled: Boolean(accessToken),
  });

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f3f5f8] text-sm text-slate-500">
        <Spin />
        <span className="ml-3">正在检查账号状态…</span>
      </div>
    );
  }

  if (user.must_change_password) {
    if (location.pathname !== SHELL_ROUTES.changePassword) {
      return <Navigate to={SHELL_ROUTES.changePassword} replace />;
    }
    return <Outlet />;
  }

  if (location.pathname === SHELL_ROUTES.changePassword) {
    return <Navigate to={SHELL_ROUTES.home} replace />;
  }

  return <Outlet />;
}
