/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ERP_API_BASE_URL?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_API_TIMEOUT_MS?: string;
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
  __WUJIE?: { mount: () => void };
  __WUJIE_MOUNT?: () => void;
  __WUJIE_UNMOUNT?: () => void;
  $wujie?: {
    props?: import('@neorvion/shared').ShellToErpProps;
    bus?: WujieBus;
    shadowRoot?: ShadowRoot;
  };
}
