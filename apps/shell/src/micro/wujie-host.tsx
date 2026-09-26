import { destroyApp, startApp } from 'wujie';
import { useEffect, useRef, type CSSProperties } from 'react';
import {
  claimMicroGeneration,
  enqueueMicroJob,
  getMicroGeneration,
} from '@/micro/lifecycle';

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
  activated?: () => void;
  loadError?: (url: string, e: Error) => void;
}

function toError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

/**
 * 使用官方 startApp / destroyApp。
 * 不用 wujie-react@1.0.29：它把启动队列写到 this.name（始终 undefined），
 * StrictMode 下会并行 startApp。
 *
 * alive=true 时，React 卸载只让 wujie-app 走 disconnectedCallback → unmount/deactivated，
 * 不调用 destroyApp。真正销毁走 destroyMicroApp。
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
  activated,
  loadError,
}: WujieHostProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef({
    url,
    sync,
    fiber,
    alive,
    prefix,
    props,
    degrade,
    afterMount,
    activated,
    loadError,
  });
  optionsRef.current = {
    url,
    sync,
    fiber,
    alive,
    prefix,
    props,
    degrade,
    afterMount,
    activated,
    loadError,
  };

  useEffect(() => {
    const el = elRef.current;
    if (!el) {
      return undefined;
    }

    let active = true;
    const generation = claimMicroGeneration(name);

    void enqueueMicroJob(name, async () => {
      if (!active) {
        return;
      }
      try {
        await startApp({
          el: elRef.current ?? el,
          name,
          url: optionsRef.current.url,
          sync: optionsRef.current.sync,
          fiber: optionsRef.current.fiber,
          alive: optionsRef.current.alive,
          prefix: optionsRef.current.prefix,
          props: optionsRef.current.props,
          degrade: optionsRef.current.degrade,
          afterMount: optionsRef.current.afterMount,
          activated: optionsRef.current.activated,
          loadError: optionsRef.current.loadError,
        });
      } catch (error) {
        if (active && getMicroGeneration(name) === generation) {
          optionsRef.current.loadError?.(optionsRef.current.url, toError(error));
        }
        return;
      }
      if (getMicroGeneration(name) !== generation) {
        return;
      }
      if (!active && !optionsRef.current.alive) {
        destroyApp(name);
      }
    });

    return () => {
      active = false;
      if (optionsRef.current.alive) {
        return;
      }
      void enqueueMicroJob(name, async () => {
        if (getMicroGeneration(name) !== generation) {
          return;
        }
        destroyApp(name);
      });
    };
  }, [name, props]);

  const style: CSSProperties = { width, height };
  return <div ref={elRef} style={style} />;
}
