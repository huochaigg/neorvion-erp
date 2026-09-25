import {
  AppstoreOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons';
import type { ComponentType } from 'react';
import type { IconName } from './types';

export const ICON_MAP: Record<IconName, ComponentType<{ className?: string }>> = {
  DashboardOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
};
