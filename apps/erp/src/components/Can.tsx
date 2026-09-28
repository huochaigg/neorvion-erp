import { cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import type { PermissionMode } from '@neorvion/shared';
import { Tooltip } from 'antd';
import { usePermissions } from '@/hooks/usePermissions';

interface CanProps {
  permission?: string;
  permissions?: readonly string[];
  mode?: PermissionMode;
  fallback?: 'hide' | 'disable';
  children: ReactNode;
}

function requiredCodes(permission?: string, permissions?: readonly string[]): string[] {
  if (permissions?.length) {
    return [...permissions];
  }
  return permission ? [permission] : [];
}

export function Can({
  permission,
  permissions,
  mode = 'all',
  fallback = 'hide',
  children,
}: CanProps) {
  const access = usePermissions();
  const codes = requiredCodes(permission, permissions);
  if (access.isLoading) {
    return fallback === 'hide' ? null : children;
  }
  const allowed = access.can(codes, mode);
  if (allowed) {
    return children;
  }
  if (fallback === 'hide') {
    return null;
  }
  const child = isValidElement(children) ? children : null;
  if (child) {
    const disabledChild = cloneElement(child as ReactElement<{ disabled?: boolean }>, {
      disabled: true,
    });
    return (
      <Tooltip title="无权限">
        <span className="inline-flex">{disabledChild}</span>
      </Tooltip>
    );
  }
  return null;
}
