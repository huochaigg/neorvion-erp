export interface AliveSandboxProbe {
  present: boolean;
  stale: boolean;
}

/** 曾经画出过内容。React 18 的 render 是异步的，刚 mount 完 #root 仍可能是空的，不能据此判定死亡。 */
const sawContent = new Set<string>();

export function forgetSandboxContent(name: string) {
  sawContent.delete(name);
}

interface WujieSandboxRef {
  shadowRoot?: ShadowRoot | null;
  iframe?: HTMLIFrameElement | null;
  provide?: { props?: object };
}

interface SandboxWindow extends Window {
  __POWERED_BY_WUJIE__?: boolean;
  __WUJIE?: WujieSandboxRef;
}

interface InjectedWindow extends Window {
  __WUJIE_INJECT?: {
    idToSandboxMap?: Map<string, { wujie?: WujieSandboxRef }>;
  };
}

function sandboxCacheMap() {
  return (window as InjectedWindow).__WUJIE_INJECT?.idToSandboxMap ?? null;
}

function cachedSandbox(name: string) {
  return sandboxCacheMap()?.get(name)?.wujie ?? null;
}

function sandboxIframe(name: string): HTMLIFrameElement | null {
  const iframe = document.querySelector(`iframe[name="${CSS.escape(name)}"]`);
  return iframe instanceof HTMLIFrameElement ? iframe : null;
}

/** 无界保活把实例留在内存里。浏览器回收隐藏 iframe 后，这里会变成空文档。 */
export function probeAliveSandbox(name: string): AliveSandboxProbe {
  const iframe = sandboxIframe(name);
  if (!iframe) {
    return { present: false, stale: false };
  }

  let sandboxWindow: SandboxWindow | null = null;
  try {
    sandboxWindow = iframe.contentWindow as SandboxWindow | null;
  } catch {
    return { present: true, stale: true };
  }
  if (!sandboxWindow?.__POWERED_BY_WUJIE__) {
    return { present: true, stale: true };
  }

  const shadowRoot = sandboxWindow.__WUJIE?.shadowRoot ?? null;
  if (!shadowRoot) {
    return { present: true, stale: sawContent.has(name) };
  }
  const root = shadowRoot.querySelector('#root');
  if (!root || root.childElementCount === 0) {
    return { present: true, stale: sawContent.has(name) };
  }
  sawContent.add(name);
  return { present: true, stale: false };
}

function delay(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

/** Access Token 刷新后写回保活沙箱。子应用每次请求都读 $wujie.props，不能等下一次 startApp。 */
export function syncTokenToAliveSandboxes(token: string) {
  for (const node of document.querySelectorAll('iframe')) {
    if (!(node instanceof HTMLIFrameElement)) {
      continue;
    }
    try {
      const sandbox = (node.contentWindow as SandboxWindow | null)?.__WUJIE;
      if (!sandbox?.provide?.props) {
        continue;
      }
      sandbox.provide.props = { ...sandbox.provide.props, token };
    } catch {
      // 沙箱窗口已经失效时，下一次激活会走重建。
    }
  }
}

/**
 * destroyApp 不返回 Promise。iframe 拆掉之前如果再 startApp，
 * 官方会走保活的 active() 直接返回，空实例就一直被复用。
 */
export async function releaseSandbox(name: string) {
  const deadline = Date.now() + 500;
  while (Date.now() < deadline) {
    if (!sandboxIframe(name) && !cachedSandbox(name)) {
      return;
    }
    await delay(16);
  }
  const sandbox = cachedSandbox(name);
  try {
    sandbox?.iframe?.remove();
    if (sandbox) {
      sandbox.iframe = null;
    }
  } catch {
    // 沙箱窗口已经不可用时，直接丢掉缓存条目。
  }
  sandboxIframe(name)?.remove();
  sandboxCacheMap()?.delete(name);
  forgetSandboxContent(name);
}
