import {
  AccountBookOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  CarOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  RollbackOutlined,
  SettingOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
} from '@ant-design/icons';
import type { ComponentType } from 'react';
import type { IconName } from './types';

export const ICON_MAP: Record<IconName, ComponentType<{ className?: string }>> = {
  DashboardOutlined,
  BarChartOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  SettingOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  AccountBookOutlined,
  CarOutlined,
  RollbackOutlined,
};
