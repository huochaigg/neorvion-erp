import type { AppRoute } from './types';

/**
 * ERP 业务路由与菜单的唯一配置来源。
 * 主应用只挂载 /erp，不维护这些路径。
 */
export const routes: AppRoute[] = [
  {
    path: '/dashboard',
    name: 'Dashboard',
    title: '工作台',
    description: 'ERP 子应用已接入。商品、库存、订单等业务页面从后续里程碑实现。',
    icon: 'DashboardOutlined',
    showInMenu: true,
    sort: 10,
    component: 'Dashboard',
  },
  {
    path: '/products',
    name: 'Products',
    title: '商品管理',
    icon: 'AppstoreOutlined',
    showInMenu: true,
    sort: 20,
    redirect: '/products/list',
    children: [
      {
        path: '/products/archive',
        name: 'ProductArchive',
        title: '商品档案',
        showInMenu: true,
        sort: 10,
        redirect: '/products/list',
        children: [
          {
            path: '/products/list',
            name: 'ProductList',
            title: '商品列表',
            description: 'M3 将实现 SPU / SKU、编码与状态筛选。',
            showInMenu: true,
            sort: 10,
            component: 'Placeholder',
          },
        ],
      },
      {
        path: '/products/create',
        name: 'ProductCreate',
        title: '新增商品',
        description: '占位页，不在菜单中展示。',
        showInMenu: false,
        activeMenu: '/products/list',
        component: 'Placeholder',
      },
      {
        path: '/products/:id/edit',
        name: 'ProductEdit',
        title: '编辑商品',
        description: '占位页，访问时菜单保持商品列表选中。',
        showInMenu: false,
        activeMenu: '/products/list',
        component: 'Placeholder',
      },
      {
        path: '/products/:id',
        name: 'ProductDetail',
        title: '商品详情',
        description: '占位页，访问时菜单保持商品列表选中。',
        showInMenu: false,
        activeMenu: '/products/list',
        component: 'Placeholder',
      },
    ],
  },
  {
    path: '/inventory',
    name: 'Inventory',
    title: '库存管理',
    icon: 'DatabaseOutlined',
    showInMenu: true,
    sort: 30,
    redirect: '/inventory/list',
    children: [
      {
        path: '/inventory/list',
        name: 'InventoryList',
        title: '库存列表',
        description: 'M3 将实现实际库存、预占库存与库存流水。',
        showInMenu: true,
        sort: 10,
        component: 'Placeholder',
      },
    ],
  },
  {
    path: '/warehouses',
    name: 'Warehouses',
    title: '仓库',
    description: 'M3 将实现仓库启停与库存查询。',
    icon: 'ShopOutlined',
    showInMenu: true,
    sort: 40,
    component: 'Placeholder',
  },
  {
    path: '/orders',
    name: 'Orders',
    title: '订单',
    description: 'M5 将实现审核、预占、出库与发货。',
    icon: 'ShoppingCartOutlined',
    showInMenu: true,
    sort: 50,
    component: 'Placeholder',
  },
];

export const DEFAULT_REDIRECT = '/dashboard';
