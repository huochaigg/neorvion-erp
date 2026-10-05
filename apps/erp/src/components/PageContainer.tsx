import type { ReactNode } from 'react';

interface PageContainerProps {
  children: ReactNode;
}

export function ListPageContainer({ children }: PageContainerProps) {
  return <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">{children}</div>;
}

export function ListToolbar({ children }: PageContainerProps) {
  return <div className="mb-3 shrink-0">{children}</div>;
}

export function ListTableArea({ children }: PageContainerProps) {
  return <div className="min-h-0 flex-1 overflow-hidden">{children}</div>;
}

export function FormPageContainer({ children }: PageContainerProps) {
  return <div className="h-full min-h-0 flex-1 overflow-y-auto">{children}</div>;
}
