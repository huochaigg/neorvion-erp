import type { ComponentClass } from 'react';
import WujieReact from 'wujie-react';

export interface WujieHostProps {
  width?: string;
  height?: string;
  name: string;
  url: string;
  sync?: boolean;
  fiber?: boolean;
  props?: object;
  afterMount?: () => void;
  loadError?: (url: string, error: Error) => void;
}

export const WujieHost = WujieReact as unknown as ComponentClass<WujieHostProps>;

export const { setupApp } = WujieReact;
