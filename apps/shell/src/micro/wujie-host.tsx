import type { ShellToErpProps } from '@neorvion/shared';
import { destroyApp, startApp, type plugin } from 'wujie';
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import {
  claimMicroGeneration,
  enqueueMicroJob,
  getMicroGeneration,
} from '@/micro/lifecycle';
import { forgetSandboxContent, probeAliveSandbox, releaseSandbox } from '@/micro/sandbox-health';
import { setupMicroApp } from '@/micro/setup';

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
  plugins?: plugin[];
  degrade?: boolean;
  /** 重建前刷新 Access Token。失败表示会话已结束，调用方会送去登录页。 */
  prepareRestart?: () => Promise<string>;
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
 * 隐藏 iframe 被浏览器清成空白时，先销毁再启动，避免保活把空 Shadow 反复挂回来。
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
  plugins,
  degrade,
  prepareRestart,
  afterMount,
  activated,
  loadError,
}: WujieHostProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const [bootId, setBootId] = useState(0);
  const optionsRef = useRef({
    url,
    sync,
    fiber,
    alive,
    prefix,
    props,
    plugins,
    degrade,
    prepareRestart,
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
    plugins,
    degrade,
    prepareRestart,
    afterMount,
    activated,
    loadError,
  };

  useEffect(() => {
    if (!alive) {
      return undefined;
    }

    const recoverIfNeeded = () => {
      if (document.visibilityState !== 'visible') {
        return;
      }
      if (!probeAliveSandbox(name).stale) {
        return;
      }
      setBootId((current) => current + 1);
    };

    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        recoverIfNeeded();
      }
    };

    document.addEventListener('visibilitychange', recoverIfNeeded);
    window.addEventListener('pageshow', onPageShow);
    return () => {
      document.removeEventListener('visibilitychange', recoverIfNeeded);
      window.removeEventListener('pageshow', onPageShow);
    };
  }, [alive, name]);

  useEffect(() => {
    const el = elRef.current;
    if (!el) {
      return undefined;
    }

    let active = true;
    const generation = claimMicroGeneration(name);

    void enqueueMicroJob(name, async () => {
      if (!active || getMicroGeneration(name) !== generation) {
        return;
      }

      const current = optionsRef.current;
      const rebuild = Boolean(current.alive && probeAliveSandbox(name).stale);

      if (rebuild) {
        console.info('[erp-micro] 保活沙箱已被浏览器清空，重新挂载', { name });
        if (current.prepareRestart) {
          try {
            const token = await current.prepareRestart();
            const previous = optionsRef.current.props as ShellToErpProps | undefined;
            if (previous) {
              optionsRef.current = {
                ...optionsRef.current,
                props: { ...previous, token },
              };
            }
          } catch {
            return;
          }
        }
        if (!active || getMicroGeneration(name) !== generation) {
          return;
        }
        forgetSandboxContent(name);
        destroyApp(name);
        await releaseSandbox(name);
        if (!active || getMicroGeneration(name) !== generation) {
          return;
        }
      }

      setupMicroApp(name);
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
          plugins: optionsRef.current.plugins,
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
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          probeAliveSandbox(name);
        });
      });
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
  }, [bootId, name]);

  useEffect(() => {
    const iframe = document.querySelector(`iframe[name="${CSS.escape(name)}"]`);
    if (!(iframe instanceof HTMLIFrameElement) || !props) {
      return;
    }
    try {
      const sandboxWindow = iframe.contentWindow as
        | (Window & { __WUJIE?: { provide?: { props?: object } } })
        | null;
      if (sandboxWindow?.__WUJIE?.provide) {
        sandboxWindow.__WUJIE.provide.props = props;
      }
    } catch {
      // 沙箱窗口已被浏览器回收时，交给可见性恢复去重建。
    }
  }, [name, props]);

  const style: CSSProperties = { width, height };
  return <div ref={elRef} style={style} />;
}
