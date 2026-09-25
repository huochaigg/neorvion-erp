import { Card } from 'antd';
import { PageHeader } from '@/components/PageHeader';
import { StatusTag } from '@/components/StatusTag';
import type { PageProps } from '@/router/types';

export function PlaceholderPage({ title = '占位页', description }: PageProps) {
  return (
    <div>
      <PageHeader
        title={title}
        description={description}
        extra={<StatusTag>后续里程碑</StatusTag>}
      />
      <Card>
        <p className="m-0 text-sm text-slate-600">
          当前仅提供路由与布局占位，避免 M1 过早展开业务实现。
        </p>
      </Card>
    </div>
  );
}
