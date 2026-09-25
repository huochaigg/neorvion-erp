import { Breadcrumb } from 'antd';
import { Link } from 'react-router-dom';
import { getBreadcrumb } from '@/router/match';
import { routes } from '@/router/routes';

interface AppBreadcrumbProps {
  pathname: string;
}

export function AppBreadcrumb({ pathname }: AppBreadcrumbProps) {
  const items = getBreadcrumb(routes, pathname);
  if (items.length === 0) {
    return null;
  }
  return (
    <Breadcrumb
      className="mb-4"
      items={items.map((item, index) => {
        const isLast = index === items.length - 1;
        const href = item.redirect ?? (item.component ? item.path : undefined);
        return {
          title: isLast || !href ? item.title : <Link to={href}>{item.title}</Link>,
        };
      })}
    />
  );
}
