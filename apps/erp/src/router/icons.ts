import {
  AccountBookOutlined,
  AppstoreOutlined,
  CarOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  SettingOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons';
import type { ComponentType } from 'react';
import type { IconName } from './types';

export const ICON_MAP: Record<IconName, ComponentType<{ className?: string }>> = {
  DashboardOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  SettingOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  AccountBookOutlined,
  CarOutlined,
};
