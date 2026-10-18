import { Card, Spin } from 'antd';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface KpiCardProps {
  title: string;
  value: ReactNode;
  hint?: string;
  loading?: boolean;
  to?: string;
}

export function KpiCard({ title, value, hint, loading, to }: KpiCardProps) {
  const body = (
    <Card size="small" hoverable={Boolean(to)} className="h-full">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-1 text-xl font-semibold text-slate-900">
        {loading ? <Spin size="small" /> : value}
      </div>
      {hint ? <div className="mt-1 text-xs text-slate-400">{hint}</div> : null}
    </Card>
  );
  if (!to) {
    return body;
  }
  return (
    <Link to={to} className="block h-full no-underline">
      {body}
    </Link>
  );
}

export function KpiGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-3 2xl:grid-cols-6">{children}</div>
  );
}

export function ChartGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">{children}</div>;
}
