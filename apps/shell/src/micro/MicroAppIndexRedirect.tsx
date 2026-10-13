import { ERP_APP_NAME, KNOWLEDGE_APP_NAME } from '@neorvion/shared';
import { Navigate } from 'react-router-dom';
import { getMicroApp, getMicroAppEntryHref } from '@/micro/apps';
import { getLastMicroHref } from '@/micro/last-location';

export function MicroAppIndexRedirect({ name }: { name: string }) {
  const app = getMicroApp(name);
  return <Navigate to={getMicroAppEntryHref(app, getLastMicroHref(name))} replace />;
}

export function ErpIndexRedirect() {
  return <MicroAppIndexRedirect name={ERP_APP_NAME} />;
}

export function KnowledgeIndexRedirect() {
  return <MicroAppIndexRedirect name={KNOWLEDGE_APP_NAME} />;
}
