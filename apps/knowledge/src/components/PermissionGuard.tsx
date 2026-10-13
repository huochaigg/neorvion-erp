import { PERMISSION_CODE } from '@neorvion/shared';
import { Result, Spin } from 'antd';
import type { ReactNode } from 'react';
import { usePermissions } from '@/hooks/usePermissions';

export function ForbiddenPage() {
  return (
    <div className="flex h-full min-h-0 items-center justify-center">
      <Result
        status="403"
        title="无权限"
        subTitle="当前企业身份无法访问 AI 知识库。这不是登录失效，请联系管理员分配角色。"
      />
    </div>
  );
}

export function PermissionGuard({ children }: { children: ReactNode }) {
  const { tenantId, hasPermission, isLoading, isError, errorMessage } = usePermissions();
  if (tenantId != null && isLoading) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (tenantId != null && isError) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center">
        <Result status="error" title="无法校验权限" subTitle={errorMessage || '请稍后重试'} />
      </div>
    );
  }
  if (tenantId != null && !hasPermission(PERMISSION_CODE.knowledgeRead)) {
    return <ForbiddenPage />;
  }
  return children;
}
