# ERP 路由与菜单（V2.1.1）

ERP 业务路由只放在子应用内部：`apps/erp/src/router/routes.ts`。

`packages/shared` 只保留主应用需要的挂载约定：

- `SHELL_ROUTES`：主应用 `/`、`/login`、`/register`、`/erp`
- `ERP_BASENAME`：主应用挂载前缀 `/erp`
- `ERP_DEFAULT_PATH`：打开 ERP 时的默认落地页 `/dashboard`

不要把商品、库存等业务路径再写进 shared。

## 配置规则

`routes.ts` 是 **React Router 与 Ant Design Menu 的唯一来源**。

| 字段 | 作用 |
| --- | --- |
| `path` / `name` | 稳定身份。不要用 `title` 判断路由 |
| `title` | 菜单文案、面包屑、页头 |
| `icon` | 仅允许 `icons.ts` 里登记过的图标名 |
| `showInMenu` | `false` 时不出现在侧栏，但仍可访问 |
| `redirect` | 分组菜单没有自己的页面时，跳到第一个子页 |
| `activeMenu` | 隐藏页（详情/新增/编辑）高亮哪一项菜单 |
| `permission` | 预留给后续 RBAC，当前不拦截 |
| `sort` | 同级排序 |
| `component` | 页面组件键，映射在 `pages.tsx`，支持懒加载 |
| `children` | 递归表达一、二、三级菜单 |

## 如何添加菜单

一级（直接对应页面）：

```ts
{
  path: '/warehouses',
  name: 'Warehouses',
  title: '仓库',
  icon: 'ShopOutlined',
  showInMenu: true,
  component: 'Placeholder',
}
```

二级 / 三级：用 `children`。父级没有页面时写 `redirect`，避免点进去空白。

```ts
{
  path: '/products',
  name: 'Products',
  title: '商品管理',
  icon: 'AppstoreOutlined',
  showInMenu: true,
  redirect: '/products/list',
  children: [
    {
      path: '/products/archive',
      name: 'ProductArchive',
      title: '商品档案',
      showInMenu: true,
      redirect: '/products/list',
      children: [
        {
          path: '/products/list',
          name: 'ProductList',
          title: '商品列表',
          showInMenu: true,
          component: 'Placeholder',
        },
      ],
    },
  ],
}
```

## 不显示在菜单中的详情页

```ts
{
  path: '/products/:id',
  name: 'ProductDetail',
  title: '商品详情',
  showInMenu: false,
  activeMenu: '/products/list',
  component: 'Placeholder',
}
```

访问 `/products/42` 时侧栏仍选中「商品列表」，并展开「商品管理 / 商品档案」。

新增页 `/products/create`、编辑页 `/products/:id/edit` 同样设置 `activeMenu: '/products/list'`。

## 菜单与 Router 如何共用配置

1. `build-routes.tsx` 把配置拍平，生成 `<Route>`。
2. `menu.tsx` 递归生成 Menu `items`，跳过 `showInMenu: false`。
3. `match.ts` 按 `path` 匹配当前 URL（静态段优先于 `:id`），计算选中项、展开项和面包屑。
4. 页面组件不要写进 `routes.ts`，只写 `component: 'Dashboard'` 这类键，由 `pages.tsx` 懒加载。

## 微前端

ERP **不要**设置 `basename=/erp`。

- 独立：`http://localhost:8016/products/list`
- 嵌入：主应用地址 `http://localhost:8015/erp/products/list`，无界 `prefix` 把它映射成子应用的 `/products/list`

主应用只负责 `/erp/*` 入口，不维护 ERP 侧栏。
