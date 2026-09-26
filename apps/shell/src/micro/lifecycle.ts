import { destroyApp } from 'wujie';
import { MICRO_APPS } from '@/micro/apps';
import { clearAllLastMicroHrefs, clearLastMicroHref } from '@/micro/last-location';

const startQueues = new Map<string, Promise<unknown>>();
const generations = new Map<string, number>();

export function enqueueMicroJob(name: string, job: () => Promise<unknown>) {
  const next = (startQueues.get(name) ?? Promise.resolve())
    .catch(() => undefined)
    .then(job);
  startQueues.set(name, next);
  return next;
}

export function claimMicroGeneration(name: string): number {
  const next = (generations.get(name) ?? 0) + 1;
  generations.set(name, next);
  return next;
}

export function getMicroGeneration(name: string): number {
  return generations.get(name) ?? 0;
}

export function destroyMicroApp(name: string) {
  return enqueueMicroJob(name, async () => {
    claimMicroGeneration(name);
    destroyApp(name);
    clearLastMicroHref(name);
  });
}

export function destroyAllMicroApps() {
  for (const app of MICRO_APPS) {
    void destroyMicroApp(app.name);
  }
  clearAllLastMicroHrefs();
}
