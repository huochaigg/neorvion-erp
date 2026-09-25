/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface WujieBus {
  $on: (event: string, callback: (...args: unknown[]) => void) => void;
  $off: (event: string, callback?: (...args: unknown[]) => void) => void;
  $emit: (event: string, ...args: unknown[]) => void;
}

interface Window {
  __POWERED_BY_WUJIE__?: boolean;
  __WUJIE_MOUNT: () => void;
  __WUJIE_UNMOUNT: () => void;
  __WUJIE: { mount: () => void };
  $wujie?: {
    bus: WujieBus;
    props?: import('@neorvion/shared').ShellToErpProps;
    shadowRoot?: ShadowRoot;
  };
}
