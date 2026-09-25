import { Spin } from 'antd';
import { Suspense, type ReactNode } from 'react';
import { Navigate, Route } from 'react-router-dom';
import { PAGE_COMPONENTS } from './pages';
import { flattenRoutes } from './match';
import { DEFAULT_REDIRECT, routes } from './routes';
import type { AppRoute } from './types';

function PageFallback() {
  return (
    <div className="flex min-h-[240px] items-center justify-center">
      <Spin />
    </div>
  );
}

function RouteElement({ route }: { route: AppRoute }) {
  if (route.redirect && !route.component) {
    return <Navigate to={route.redirect} replace />;
  }
  if (!route.component) {
    return <Navigate to={route.redirect ?? DEFAULT_REDIRECT} replace />;
  }
  const Page = PAGE_COMPONENTS[route.component];
  return (
    <Suspense fallback={<PageFallback />}>
      <Page title={route.title} description={route.description} />
    </Suspense>
  );
}

export function buildRouteElements(): ReactNode {
  return flattenRoutes(routes)
    .filter((item) => item.component || item.redirect)
    .map((item) => <Route key={item.name} path={item.path} element={<RouteElement route={item} />} />);
}
