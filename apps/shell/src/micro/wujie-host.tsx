import { destroyApp, startApp } from 'wujie';
import { useEffect, useRef, type CSSProperties } from 'react';

export interface WujieHostProps {
  width?: string;
  height?: string;
  name: string;
  url: string;
  sync?: boolean;
  fiber?: boolean;
  alive?: boolean;
  prefix?: Record<string, string>;
  props?: object;
  degrade?: boolean;
  afterMount?: () => void;
  loadError?: (url: string, e: Error) => void;
}

const startQueues = new Map<string, Promise<unknown>>();

function enqueue(name: string, job: () => Promise<unknown>) {
  const next = (startQueues.get(name) ?? Promise.resolve())
    .catch(() => undefined)
    .then(job);
  startQueues.set(name, next);
  return next;
}

function toError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

/**
 * 使用官方 startApp / destroyApp。
 * 不用 wujie-react@1.0.29：它把启动队列写到 this.name（始终 undefined），
 * StrictMode 下会并行 startApp。
 */
export function WujieHost({
  width = '100%',
  height = '100%',
  name,
  url,
  sync,
  fiber,
  alive,
  prefix,
  props,
  degrade,
  afterMount,
  loadError,
}: WujieHostProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef({
    sync,
    fiber,
    alive,
    prefix,
    props,
    degrade,
    afterMount,
    loadError,
  });
  optionsRef.current = {
    sync,
    fiber,
    alive,
    prefix,
    props,
    degrade,
    afterMount,
    loadError,
  };

  useEffect(() => {
    const el = elRef.current;
    if (!el) {
      return undefined;
    }

    let active = true;

    void enqueue(name, async () => {
      if (!active) {
        return;
      }
      try {
        await startApp({
          el: elRef.current ?? el,
          name,
          url,
          ...optionsRef.current,
        });
      } catch (error) {
        if (active) {
          optionsRef.current.loadError?.(url, toError(error));
        }
        return;
      }
      if (!active) {
        destroyApp(name);
      }
    });

    return () => {
      active = false;
      void enqueue(name, async () => {
        destroyApp(name);
      });
    };
  }, [name, url]);

  const style: CSSProperties = { width, height };
  return <div ref={elRef} style={style} />;
}
