import { Card } from 'antd';
import { PageHeader } from '@/components/PageHeader';
import { StatusTag } from '@/components/StatusTag';
import { useErpTenantStore } from '@/stores/tenant-runtime';
import type { PageProps } from '@/router/types';

export function PlaceholderPage({ title = '占位页', description }: PageProps) {
  const tenantId = useErpTenantStore((state) => state.currentTenantId);
  return (
    <div>
      <PageHeader
        title={title}
        description={description}
        extra={<StatusTag>后续里程碑</StatusTag>}
      />
      <Card>
        <p className="m-0 text-sm text-slate-600">
          当前仅提供路由与布局占位。当前租户：{tenantId ?? '未选择'}。切租户后本页会按新租户重新挂载。
        </p>
      </Card>
    </div>
  );
}
