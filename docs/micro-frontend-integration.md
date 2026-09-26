# 微前端接入指南

本文说明如何把一个已有的 React 或 Vue 项目接入 Neorvion 的 Shell。阅读对象是后续要接 SCM、CRM 的开发者，不要求先读过 Wujie 源码。

当前仓库里 **已经落地并验证过的子应用只有 ERP**。文中凡标注「已有代码」的，都能在仓库里找到对应文件；标注「示意」或「参考模板」的，是按同一套约定写出的扩展示例，本仓库尚未实现、也未跑过浏览器验证。

相关文件：

| 路径 | 职责 |
| --- | --- |
| `apps/shell/src/micro/apps.ts` | 子应用注册表 |
| `apps/shell/src/micro/setup.ts` | 启动前调用官方 `setupApp`，`sync: false`，不预加载 |
| `apps/shell/src/micro/wujie-host.tsx` | 调用官方 `startApp` / `destroyApp`；alive 时卸载不销毁 |
| `apps/shell/src/micro/lifecycle.ts` | 串行队列、generation、真正销毁入口 |
| `apps/shell/src/micro/route-sync.ts` | Shell 侧 pathname 双向同步 |
| `apps/shell/src/micro/css-plugins.ts` | 按需 CSS 插件 |
| `apps/shell/src/micro/ErpMicroApp.tsx` | ERP 薄包装：拼 URL、传 props、错误回退 |
| `apps/erp/src/micro/WujieRouteBridge.tsx` | ERP 侧路由桥 |
| `apps/shell/src/app/router.tsx` | 主应用挂载 `/erp/*` |
| `apps/shell/src/main.tsx` | 渲染前 `setupMicroApps()` |
| `apps/erp/src/main.tsx` | 子应用生命周期 |
| `packages/shared/src/types/bridge.ts` | props 与 `MICRO_EVENTS` |
| `docs/micro-frontend-interview.md` | 白屏排查与架构复盘（面试向） |

默认模式是 **Shadow DOM**（`degrade: false`）。不要为了排障把降级 iframe 当成正式方案。

---

## 1. 架构介绍

### 1.1 四层关系

```text
浏览器地址栏
  └── Shell（apps/shell，React 19 + React Router）
        ├── 登录 / 鉴权 / 顶部导航 / 工作台
        ├── setupMicroApps()          只注册，不启动
        ├── MICRO_APPS 注册表         name、入口、插件
        └── 进入 /erp/* 时渲染 ErpMicroApp
              └── WujieHost           按 name 串行 startApp / destroyApp
                    └── wujie@1.0.29
                          ├── 隐藏 iframe：JS 沙箱
                          └── <wujie-app> Shadow DOM：CSS 沙箱
                                └── ERP（apps/erp）自己的 React 树
```

首页 `/` 只渲染 `HomePage`，**不会**创建 ERP 的 Wujie 实例。只有路由进到 `/erp/*` 才 `startApp`。

### 1.2 Shell 统一提供的能力

- 登录、Refresh Cookie、路由守卫（`RequireAuth`）。
- 子应用注册、启动、卸载、同一 `name` 上的串行队列。
- 主应用路径与子应用入口 URL 的拼接（`buildMicroAppUrl`）。
- 把 token / tenantId / user 通过 Wujie `props` 注入。
- 路由同步开关：`sync: true`，查询参数名为子应用 `name`。

### 1.3 子应用需要自己做的事

- 按 Wujie 约定实现 `__WUJIE_MOUNT` / `__WUJIE_UNMOUNT`，Vite ESM 下再调用 `__WUJIE.mount()`。
- 内部路由用自己的路径（`/dashboard`），不要带 `/erp`。
- 从 `window.$wujie.props` 读 Shell 传入的状态，不要读 Shell 的 Zustand。
- 若使用 Tailwind v4 + Shadow DOM，由 **Shell 注册表** 为该应用挂 CSS 插件，子应用不必改 Wujie。
- 若使用 Ant Design 弹层，在子应用 `ConfigProvider` 里指定 `getPopupContainer`。

子应用 **不要** 安装 `wujie`，也 **不要** 调用 `setupApp` / `startApp` / `destroyApp`。

### 1.4 为什么不用 wujie-react

仓库曾经依赖 `wujie-react@1.0.29`。它的 `execStartApp` 把队列写到 `window.__WUJIE_QUEUE[this.name]`。这是 class 组件，`this.name` 始终是 `undefined`，而 `componentDidMount` 却用 `this.props.name` 去读队列。React 19 StrictMode 二次挂载时，两次 `startApp` 会并行。

Shell 因此改为直接依赖 `wujie@1.0.29`（见 `apps/shell/package.json`），用 `WujieHost` 包一层。Host **只调用** 官方 `setupApp`、`startApp`、`destroyApp`，不实现 iframe 沙箱、不实现 Shadow DOM、不改 Wujie 源码。

`apps/erp/package.json` 没有 `wujie` 或 `wujie-react`。这是有意的：接入成本停在生命周期钩子，而不是再引入一套微前端 SDK。

---

## 2. 主应用接入步骤

### 2.1 在注册表增加子应用（已有：ERP）

`apps/shell/src/micro/apps.ts` 当前真实配置：

```ts
export const MICRO_APPS: MicroAppDefinition[] = [
  {
    name: ERP_APP_NAME,          // 'erp'
    basename: ERP_BASENAME,      // '/erp'
    defaultPath: ERP_DEFAULT_PATH, // '/dashboard'
    getEntry: () => (import.meta.env.VITE_ERP_ENTRY || 'http://localhost:8016').replace(/\/$/, ''),
    fiber: false,
    degrade: false,
    alive: true,
    plugins: [tailwindV4ShadowCssPlugin()],
  },
];
```

常量来自 `packages/shared`：`ERP_APP_NAME`（`src/constants/app.ts`）、`ERP_BASENAME` / `ERP_DEFAULT_PATH`（`src/constants/routes.ts`）。

`apps/shell/src/micro/setup.ts` 会遍历清单并调用官方 `setupApp`：

```ts
setupApp({
  name: app.name,
  exec: false,                 // 不预执行、不预加载
  sync: false,                 // 不用 ?erp=，改由 Shell pathname 双向同步
  alive: app.alive ?? false,
  fiber: app.fiber ?? false,
  degrade: app.degrade ?? false,
  prefix: { [app.name]: app.basename },  // 保留给 Wujie，但原生 sync 已关闭
  plugins: app.plugins,
});
```

`apps/shell/src/main.tsx` 在 `createRoot` 之前调用 `setupMicroApps()`。这里只缓存配置，不会去拉 ERP 的 HTML。

### 2.2 配置项实际含义

| 字段 | 当前 ERP 取值 | 含义 |
| --- | --- | --- |
| `name` | `'erp'` | Wujie 实例 id，也是 bus 事件里的应用名 |
| `basename` | `'/erp'` | 主应用挂载前缀；`buildMicroAppUrl` 用它从 pathname 剥前缀 |
| `defaultPath` | `'/dashboard'` | 首次进入或没有上次路由时的落地页 |
| `getEntry()` | `VITE_ERP_ENTRY` 或 `http://localhost:8016` | 子应用 origin，**不含**业务 path |
| `url`（startApp 时） | 如 `http://localhost:8016/dashboard` | 由 `buildMicroAppUrl` 现场拼出；保活后再进入不靠改 url 切路由 |
| `prefix` | `{ erp: '/erp' }` | Wujie 短路径替换；当前关闭原生 sync，不参与地址栏 |
| `sync` | `false` | 关闭 `?erp=` 查询串同步，避免和 React Router 抢 `history.state` |
| `alive` | `true` | 离开 `/erp/*` 时不 `destroyApp`，再次进入恢复实例 |
| `fiber` | `false` | Vite ESM 脚本是异步的，关掉 fiber，避免执行时机飘 |
| `degrade` | `false` | 使用 Shadow DOM，不用降级可见 iframe |
| `exec` | `false` | 不预加载 |
| `plugins` | Tailwind v4 CSS 插件 | **按应用**挂，不是全局默认 |

`ErpMicroApp` 会显式传入 `sync={false}`、`alive`、`fiber`、`degrade`。`WujieHost` 的 effect 只依赖 `name` 与 `props`，pathname 变化不会重启沙箱。

### 2.3 Shell Router 如何挂载（已有代码）

`apps/shell/src/app/router.tsx`：

```tsx
<Route path={ERP_BASENAME} element={<ErpIndexRedirect />} />
<Route path={`${ERP_BASENAME}/`} element={<ErpIndexRedirect />} />
<Route path={`${ERP_BASENAME}/*`} element={<ErpMicroApp />} />
```

即：打开 `/erp` 视为「进入 ERP 应用」，重定向到上次路由或 `/erp/dashboard`；`/erp/dashboard`、`/erp/orders` 等是指定页面。该路由在 `RequireAuth` 内，未登录会先去登录页。

侧栏「ERP 业务」走入口恢复：`getMicroAppEntryHref(app, getLastMicroHref(app.name))`。首页上的「打开 ERP 工作台」则是指定 `/erp/dashboard`。

### 2.4 开发 / 生产入口

开发：`apps/shell/.env.example`

```text
VITE_API_BASE_URL=http://localhost:8011
VITE_ERP_ENTRY=http://localhost:8016
```

`getEntry()` 读 `import.meta.env.VITE_ERP_ENTRY`，缺省回落到 `http://localhost:8016`。

生产：把 `VITE_ERP_ENTRY` 改成 ERP 静态资源的实际 Origin（例如独立域名或 CDN）。构建时由 Vite 打进 Shell。当前 `nginx/nginx.conf` 只把 `/` 反代到 Shell `8015`，**还没有**单独的 ERP `location`；部署拆分需要另做，不要假定仓库里已经有多子应用的生产网关。

### 2.5 主应用如何传 token、tenantId、user

类型在 `packages/shared/src/types/bridge.ts`：

```ts
export interface ShellToErpProps {
  token: string | null;
  tenantId: number | null;
  user: ShellUserSnapshot | null;
}
```

`ErpMicroApp` 从 `useAuthStore`、`useShellStore`、`fetchCurrentUser` 组装后传给 `WujieHost` 的 `props`。Wujie 把它放到子应用的 `window.$wujie.props`。

ERP 侧用 `apps/erp/src/lib/runtime.ts` 的 `getShellProps()` 读取。ERP **不**调用 Refresh，只用这份 token（见 `docs/auth.md`）。

### 2.6 URL 对应关系（避免 `/erp/erp`）

`buildMicroAppUrl`（`apps.ts`）：

- 主应用 pathname `/erp` 或 `/erp/` → `http://localhost:8016/dashboard`（仅用于尚未记住上次路由时的默认入口）
- 主应用 pathname `/erp/dashboard` → `http://localhost:8016/dashboard`（剥掉 `/erp` 前缀）
- 主应用 pathname `/erp/orders` → `http://localhost:8016/orders`

子应用自己的 React Router **没有** `basename="/erp"`（见 `apps/erp/src/app/router.tsx` 的 `BrowserRouter`）。如果再给 ERP 加 `/erp` basename，嵌入后就会变成 `/erp/erp/...`。

规范地址栏是 **pathname**，不再长期使用 `?erp=`：

```text
Shell 地址栏：http://localhost:8015/erp/orders
                     └── React Router 挂载前缀 /erp
                                     └── 子应用路径 /orders
```

旧书签 `/erp/dashboard?erp=%2Forders` 会在 `ErpMicroApp` 里被 `consumeLegacyWujieSyncQuery` 一次性改写成 `/erp/orders`。

### 2.7 启动、卸载、错误回退与真正销毁

- **启动**：`WujieHost` 在 `useEffect` 里按 `name` 串行 `startApp`。
- **失活**：`alive: true` 时，React 卸载 Host **不**调用 `destroyApp`。`wujie-app` 的 `disconnectedCallback` 会走到官方 `sandbox.unmount()`，对保活应用只触发 `deactivated`，不拆 React 树。
- **StrictMode**：第一次 effect 被取消后，已入队的 `startApp` 若尚未开始会跳过；若已完成且 `alive`，不销毁，第二次 `startApp` 走官方 `active()` 再挂回新容器。generation 保证旧 cleanup 不会 `destroyApp` 掉新实例。
- **真正销毁**：`destroyMicroApp` / `destroyAllMicroApps`（`apps/shell/src/micro/lifecycle.ts`）。退出登录、Refresh 失败、`setCurrentTenantId` 变化时调用。
- **异常**：`startApp` 抛错时调用 `loadError`。

不要在子应用里再包一层 `startApp`。不要靠首页里藏一个隐藏 ERP DOM 假装保活。

### 2.8 新增 SCM（示意，本仓库没有这份代码）

下面不是现有文件，只说明按 ERP 同样步骤要改什么。

1. `packages/shared` 增加 `SCM_APP_NAME = 'scm'`、`SCM_BASENAME = '/scm'`、`SCM_DEFAULT_PATH`，以及如需的 `ShellToScmProps`。
2. `apps.ts` 的 `MICRO_APPS` 再推一条：

```ts
{
  name: 'scm',
  basename: '/scm',
  defaultPath: '/dashboard',
  getEntry: () => (import.meta.env.VITE_SCM_ENTRY || 'http://localhost:8017').replace(/\/$/, ''),
  fiber: false,
  degrade: false,
  alive: true,
  // 若 SCM 不是 Tailwind v4，不要挂 tailwindV4ShadowCssPlugin()
}
```

3. `apps/shell/.env.example` 增加 `VITE_SCM_ENTRY=http://localhost:8017`。
4. `router.tsx` 增加 `/scm` 的入口 Redirect（恢复上次路由）和 `/scm/*` 包装组件。
5. 侧栏「进入 SCM」走 `getMicroAppEntryHref`；若有「打开某页」则 `navigate('/scm/...')`。
6. 子应用实现与 ERP 相同的 `MICRO_EVENTS` 路由桥（React 用 `navigate`，Vue 用 `router.push`）。它仍然 **不要** 依赖 `wujie`。
7. 包装组件复用 `useMicroHostRouteSync`，不要再打开 Wujie `sync: true`。

---

## 3. React 子应用接入（以当前 ERP 为准）

### 3.1 依赖

ERP（`apps/erp/package.json`）需要：React 19、react-dom、react-router-dom，以及业务库（antd、axios 等）。

**不需要**安装 `wujie`、`wujie-react`。微前端运行时由主应用注入 `window.__POWERED_BY_WUJIE__`、`window.__WUJIE`、`window.$wujie`。

### 3.2 `main.tsx` 最小模板（已有代码）

文件：`apps/erp/src/main.tsx`。

```tsx
let root: Root | null = null;

function mountApp() {
  const container = document.getElementById('root');
  if (!container) {
    throw new Error('未找到 #root 挂载节点');
  }
  if (!root) {
    root = createRoot(container);
  }
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

function unmountApp() {
  root?.unmount();
  root = null;
}

if (window.__POWERED_BY_WUJIE__) {
  window.__WUJIE_MOUNT = mountApp;
  window.__WUJIE_UNMOUNT = unmountApp;
  // Vite 模块异步加载，必须主动触发无界 mount，避免白屏。
  window.__WUJIE.mount();
} else {
  mountApp();
}
```

要点：

- `window.__POWERED_BY_WUJIE__` 为真表示跑在沙箱里。
- 嵌入时不要在模块顶层直接 `createRoot`，等 Wujie 调 `__WUJIE_MOUNT`。
- Vite 打出来的是 `type="module"`，Wujie 执行完脚本时 `__WUJIE_MOUNT` 可能还没挂上，所以入口末尾要 `__WUJIE.mount()`，让框架在钩子就绪后再 mount。这是当前 ERP 已经在用的写法。
- `unmount` 之后把 `root` 置 `null`。React 19 不能对已 `unmount` 的 Root 再次 `render`，下次必须 `createRoot`。

独立运行（直接打开 `http://localhost:8016`）走 `else`，与是否被 Shell 加载无关。

### 3.3 路由 basename

`apps/erp/src/app/router.tsx` 使用无 basename 的 `BrowserRouter`。业务路径在 `apps/erp/src/router/routes.ts`，例如 `/dashboard`、`/orders`。

嵌入后，沙箱里的 `location.pathname` 是 `/dashboard` 而不是 `/erp/dashboard`。不要给子应用设 `basename="/erp"`。

`ErpLayout` 用 `isEmbeddedInWujie()` 隐藏独立运行时的顶栏，避免和 Shell 顶栏重复。这是 UI 适配，不是 Wujie 必需。

### 3.4 接收 Shell props

```ts
// apps/erp/src/lib/runtime.ts
export function getShellProps(): ShellToErpProps {
  return (
    window.$wujie?.props ?? {
      token: null,
      tenantId: null,
      user: null,
    }
  );
}
```

独立运行时没有 Shell，`props` 为空，业务请求可能 401。这是预期行为，不要在 ERP 里再做一套登录。

### 3.5 Vite 开发与预览（已有代码）

`apps/erp/vite.config.ts`：

```ts
server: {
  host: '0.0.0.0',
  port: 8016,
  strictPort: true,
  origin: 'http://localhost:8016',
  cors: true,
  headers: { 'Access-Control-Allow-Origin': '*' },
},
preview: {
  port: 4174,
  cors: true,
  headers: { 'Access-Control-Allow-Origin': '*' },
},
```

`origin` 必须写绝对地址：Shell 在 `8015` 跨源 `fetch` 子应用 HTML，页面里的 `/src/main.tsx` 要能解析成 `http://localhost:8016/src/main.tsx`。漏配 `origin` 时，常见现象是子应用脚本 404 或打到主应用域名上。

`fiber: false` 写在 **Shell 注册表**，不是写在子应用 Vite 配置里。

### 3.6 为什么子应用不要自己 `startApp`

`startApp` 会创建 iframe、拉 HTML、启沙箱。这件事已经由进入 `/erp/*` 的 `WujieHost` 做了。子应用再调一次，等于对同一个 `name: 'erp'` 再启动，和 StrictMode 并行启动是同类问题。子应用只负责在自己的 window 上挂载 UI。

---

## 4. Vue2 / Vue3 子应用接入

**本仓库没有 Vue 子应用。** 以下按 Wujie 1.0.29 对子应用的约定（`__WUJIE_MOUNT` / `__WUJIE_UNMOUNT` / `__WUJIE.mount`）给出参考模板，**未在本项目浏览器里验证**。

Vue 子应用同样不要安装 `wujie`，不要调 `startApp`。Shell 侧接入步骤与第 2 节相同，清单里按需决定是否挂 Tailwind 插件（多数 Vue 项目不需要）。

### 4.1 Vue 3（参考模板，未验证）

```ts
import { createApp, type App as VueApp } from 'vue';
import RootApp from './App.vue';

let app: VueApp | null = null;

function mountApp() {
  if (app) return;
  app = createApp(RootApp);
  app.mount('#app');
}

function unmountApp() {
  app?.unmount();
  app = null;
}

if (window.__POWERED_BY_WUJIE__) {
  window.__WUJIE_MOUNT = mountApp;
  window.__WUJIE_UNMOUNT = unmountApp;
  window.__WUJIE.mount();
} else {
  mountApp();
}
```

不要把 React 的 `createRoot` 套到 Vue 3 上。Vue 3 对应的是 `createApp` / `app.unmount()`。

路由用 `vue-router` 的 `createWebHistory()`，history base 用 `/`，不要用 `/erp` 或 `/scm`。

### 4.2 Vue 2（参考模板，未验证）

```ts
import Vue from 'vue';
import App from './App.vue';

let instance: Vue | null = null;

function mountApp() {
  if (instance) return;
  instance = new Vue({ render: (h) => h(App) }).$mount('#app');
}

function unmountApp() {
  instance?.$destroy();
  instance = null;
  const el = document.getElementById('app');
  if (el) el.innerHTML = '';
}

if (window.__POWERED_BY_WUJIE__) {
  window.__WUJIE_MOUNT = mountApp;
  window.__WUJIE_UNMOUNT = unmountApp;
  window.__WUJIE.mount();
} else {
  mountApp();
}
```

Vue 2 没有 `createRoot`。销毁用 `$destroy()`。若使用 `vue-router@3`，`mode: 'history'`，`base: '/'`。

### 4.3 与 React 子应用的差异

| | React 19（已验证） | Vue 3 / Vue 2（未验证） |
| --- | --- | --- |
| 挂载 | `createRoot` + `render` | `createApp().mount` / `new Vue().$mount` |
| 卸载 | `root.unmount()` 后 `root = null` | `app.unmount()` / `$destroy()` |
| 样式插件 | ERP 使用 Tailwind v4 插件 | 默认不要挂该插件 |
| 弹层 | Ant Design `getPopupContainer` | Element Plus 等用自己的 `append-to` / `teleport` |
| Vite `origin` / CORS | 与 ERP 相同，必须配 | 相同 |

---

## 5. 样式隔离

### 5.1 Shadow DOM 做什么

`degrade: false` 时，Wujie 把子应用 HTML 放进自定义元素 `wujie-app` 的 open Shadow Root。子应用 CSS 默认出不了这块影子树，主应用 CSS 也进不去。JS 仍在隐藏 iframe 里跑。

Shell 的 `apps/shell/src/index.css` 只给宿主写了：

```css
wujie-app {
  display: block;
  width: 100%;
  height: 100%;
}
```

这是主应用布局需要，不是子应用主题。

### 5.2 Tailwind v4 的 `:root` 与 `:host`

`apps/erp/src/index.css` 在普通文档里把主题变量写在 `:root` 上。Shadow 里没有「文档根 html」这层匹配，`:root` 规则不会作用到影子树，主题色、spacing 会丢。

`:host` 匹配的是 Shadow Root 的宿主元素（这里是 `wujie-app`），变量才能在影子树内继承。

### 5.3 `tailwindV4ShadowCssPlugin` 做什么

`apps/shell/src/micro/css-plugins.ts` 只在 CSS 选择器位置把 `:root` 换成 `:host`，避免 `replaceAll(':root', ':host')` 误伤 `url()` 或自定义属性。

它出现在 **ERP 这一条** `MICRO_APPS` 的 `plugins` 里，不会自动套到以后的 Vue / 非 Tailwind 应用。

不要在 iframe 降级模式（`degrade: true`）里无条件做同样替换：那时样式在 iframe 的 document 上，`:root` 是正确的，改成 `:host` 主题会失效。这也是「降级能显示但样式异常」的原因之一。

Wujie 自己还会在 `getPatchStyleElements` 里把部分 `:root` 规则抄到 `:host`；ERP 仍单独挂插件，是因为 Tailwind v4 生成量大，构建期改选择器更稳。两者不冲突。

### 5.4 Ant Design 弹层

Modal、Select、Dropdown、DatePicker、Drawer 默认 `getPopupContainer` 到 `document.body`。在 Shadow DOM 里，如果挂到主应用 body，弹层会跑到影子树外面，定位和样式都会错。

ERP 在 `AppProviders` 里传入 `getPopupContainer`（`apps/erp/src/lib/runtime.ts`）：优先 `node.closest('#root')`，否则用 `$wujie.shadowRoot` 里的 `#root` 或 `body`。

这是 **Ant Design 子应用自己的配置**。未来 Vue 项目用 Element Plus，应使用其 `append-to` / Teleport，不要照搬 Antd 这段代码，也不要在 Shell 里写死一套弹层逻辑。

当前 Dashboard 没有把 Select / Modal / Drawer 的交互全部点一遍，接入新页面时仍建议按第 9 节清单自测弹层。

---

## 6. 路由同步

### 6.1 为什么关掉 Wujie 原生 `sync`

`wujie@1.0.29` 的 `syncUrlToWindow`（`esm/sync.js`）只会改主应用查询串 `?{name}=`，并 `window.history.replaceState(null, "", href)`。这会：

- 把地址栏停在进入时的 pathname（例如一直是 `/erp/dashboard`）；
- 把 React Router 的 `history.state` 写成 `null`；
- 子应用内部 `pushState` 不会在主应用产生新的 history 条目，浏览器后退无法在 ERP 页面之间移动。

因此当前 `setupApp({ sync: false })`，由 Shell 维护规范 pathname。两套机制不能同时写 History。

### 6.2 真实路径

| 角色 | 路径 |
| --- | --- |
| Shell React Router | `/erp/orders` |
| `buildMicroAppUrl` 得到的首次入口 | `http://localhost:8016/orders` |
| ERP `BrowserRouter` | `/orders` |
| 地址栏 | `http://localhost:8015/erp/orders`（无 `?erp=`） |

### 6.3 双向同步

事件在 `packages/shared`：`MICRO_EVENTS.childLocation` / `MICRO_EVENTS.hostNavigate`。Wujie `bus.$emit` 会广播到所有 EventBus 实例，主子都能听到。

| 场景 | 谁驱动 | 行为 |
| --- | --- | --- |
| 子应用菜单跳转 | ERP `WujieRouteBridge` 发 `childLocation` | Shell `navigate('/erp/orders')`，默认 push，保留 search/hash |
| Shell 菜单 / 指定链接 / 前进后退 | Shell `useMicroHostRouteSync` 发 `hostNavigate` | 保活实例里 ERP `navigate(..., { replace: true })`，不指望改 `startApp(url)` |
| 首次创建 | `startApp(url)` | iframe 初始路径等于剥前缀后的子路径 |
| 刷新 / 深层链接 | 浏览器打开 `/erp/orders` | Shell 命中 `/erp/*`，`buildMicroAppUrl` 得到 `/orders` |
| 进入应用（侧栏「ERP 业务」或 `/erp`） | `getLastMicroHref` | 恢复上次 pathname；没有则 `/erp/dashboard` |
| 进入指定页面 | 直接 `navigate('/erp/dashboard')` | 即使上次在订单页，也打开 Dashboard |
| 旧 `?erp=` 书签 | `consumeLegacyWujieSyncQuery` | replace 成规范 pathname |

循环避免：

- Shell 因子应用事件而 `navigate` 时置 `syncingFromChild`，不再回发 `hostNavigate`。
- ERP 因 `hostNavigate` 而 `navigate` 时置 `applyingHost`，不再回发 `childLocation`。
- 目标路径与当前路径相同则直接返回。
- 使用 React Router `navigate`，不手动 `history.replaceState(null, ...)`。

### 6.4 新子应用如何接路由

1. 注册 `basename`，例如 `/scm`。
2. 子应用内部路由从 `/` 开始，不要带 `/scm`。
3. 在子应用 Router 内挂与 `WujieRouteBridge` 同类的监听，`payload.name` 填自己的 `name`。
4. Shell 包装组件调用 `useMicroHostRouteSync(app)`。
5. 保持 `sync: false`。

Vue 子应用把 `navigate` 换成 `router.push` / `router.replace` 即可，事件名不变。本仓库没有 Vue 子应用，未验证。

---

## 7. 生命周期与保活

### 7.1 `alive=true` 与 `alive=false`

| | `alive=false` | `alive=true`（当前 ERP） |
| --- | --- | --- |
| 离开 `/erp/*` | Host cleanup `destroyApp` | 不 `destroyApp`；官方 `disconnectedCallback` → `unmount` → `deactivated` |
| 再次进入 | 重新拉 JS/CSS、重新 `createRoot` | `startApp` 走 `sandbox.active()`，把已有 `wujie-app` 挂回新容器，触发 `activated` |
| 页面状态 | 丢失 | React 树、QueryClient、表单还在 |

### 7.2 为什么可以保活又不把路由搅乱

以前用 `alive=false`，是因为侧栏无条件 `navigate('/erp/dashboard')`，保活会让菜单和页面不一致。现在入口和指定页分开，保活恢复的是上次路由；指定链接仍发 `hostNavigate` 覆盖子应用路径。

### 7.3 同一个 `name` 必须串行

`startApp` / `destroyApp` 共用名为 `erp` 的沙箱。`enqueueMicroJob` 把同一 name 排成一条链。`claimMicroGeneration` 防止：

```text
startApp(1) → startApp(2) → destroy(1) 误杀新实例
```

旧 cleanup 发现 generation 已变就跳过 `destroyApp`。

StrictMode（alive）：

```text
startApp(1) 若已被取消则跳过
  → 不 destroy
  → startApp(2) 复用或新建后挂到第二次容器
```

### 7.4 退出登录与租户变化

保活实例里可能还留着上一个用户的 token 和页面数据，必须拆掉：

- 侧栏退出：`destroyAllMicroApps()`（`ShellLayout`）
- Refresh 失败：`apps/shell/src/api/client.ts` 拦截器
- `setCurrentTenantId` 值变化：`shell-store`

真正销毁入口是 `destroyMicroApp(name)` / `destroyAllMicroApps()`，同时清掉 `sessionStorage` 里的上次路由。

---

## 8. 常见问题排查

### 子应用白屏

- **现象**：Shell 布局在，内容区空白。
- **排查**：Console 是否有 `_cacheListeners` / `Document.prototype` / `protocol`；Network 是否拉到 ERP HTML；`wujie-app` 的 shadow 里有没有 `#root`。
- **处理**：确认未设置 `attrs.src`；确认 Host 串行队列；确认 ERP 调用了 `__WUJIE.mount()`；用系统 Chrome，不要用会拦 iframe 的内嵌浏览器。

### 独立运行正常，嵌入失败

- **现象**：`http://localhost:8016` 正常，`http://localhost:8015/erp` 白屏或 404。
- **排查**：ERP `vite.config.ts` 的 `origin`、`cors`；Shell `VITE_ERP_ENTRY` 是否指向 8016；脚本 URL 是否变成了 `localhost:8015/src/main.tsx`。
- **处理**：补 `server.origin`，保证资源绝对地址。两端都要启动（`pnpm dev` 或分别 `dev:shell` / `dev:erp`）。

### iframe Document 未初始化

- **现象**：`Cannot read properties of undefined (reading 'prototype')`，栈在 `initIframeDom`。
- **排查**：是否给沙箱 iframe 配了 `attrs.src`（包括空白 html）；是否在初始化完成前 `destroyApp`。
- **处理**：不要传 `attrs.src`，让 1.0.29 走 blob 空文档；不要并行 `startApp`。

### `_cacheListeners` 报错

- **现象**：`Cannot set properties of null (setting '_cacheListeners')`，栈在 `patchEventListener` ← `patchRenderEffect`。
- **排查**：默认模式下 `render.head` / `render.body` 是否为 null（模板还没进 Shadow，或实例已被销毁）。
- **处理**：串行启动/销毁；不要在 `startApp` 中途拆掉同一个 name 的沙箱。`degrade: true` 会跳过这段 patch，但那不是正式方案。

### StrictMode 重复启动

- **现象**：开发模式脚本插入两遍、偶发白屏；生产（无 StrictMode）较稳定。
- **排查**：是否仍在用 `wujie-react@1.0.29` 的组件（`this.name` 队列键）。
- **处理**：只用 Shell 的 `WujieHost`。不要在子应用再 `startApp`。

### 刷新正常，客户端路由跳转白屏

- **现象**：直开 `/erp/dashboard?erp=%2Fdashboard` 可以，从 `/` 点菜单白屏。
- **排查**：跳转时还没有 `?erp=`，Wujie 可能对沙箱 iframe `replaceState`；再叠加并行 `startApp`。这是本项目已经修过的组合问题。
- **处理**：保持当前 Host 与「不设置 attrs.src」。不要用 `location.reload()` 当修复。

### Tailwind 样式丢失

- **现象**：字在、布局崩、主题色没了。
- **排查**：是否在 Shadow 里还用 `:root`；是否把 `tailwindV4ShadowCssPlugin` 套到了非 Tailwind 应用；是否 `degrade: true` 后又做了 `:root` → `:host`。
- **处理**：只给需要的应用挂该插件。降级模式下不要替换 `:root`。

### Ant Design 弹窗定位错误

- **现象**：Select / Modal 出现在主应用空白处或被裁切。
- **排查**：是否 `getPopupContainer` 指向了主 `document.body`。
- **处理**：用 ERP 的 `getPopupContainer`，挂到影子树内 `#root`。Vue 组件库用各自 API，不要共用这段 Antd 代码。

### 主子应用路由不同步

- **现象**：点了子应用菜单，地址栏 pathname 不变，或出现 `?erp=`。
- **排查**：`setupApp` 是否误开 `sync: true`；子应用是否挂了路由桥；是否错误设置了 `basename="/erp"`。
- **处理**：保持 `sync: false`；子应用路径不要带 `/erp`；用 `MICRO_EVENTS` 双向同步。

### 子应用资源 404

- **现象**：HTML 200，JS/CSS 404。
- **排查**：相对路径被解析到 Shell origin；生产环境 `VITE_ERP_ENTRY` 与真实静态地址不一致。
- **处理**：开发配 `server.origin`；生产入口只配 origin，path 仍由 `buildMicroAppUrl` 拼。

### 子应用重复挂载

- **现象**：React 报 root 已占用，或 Vue 重复 mount。
- **排查**：`__WUJIE_MOUNT` 是否在未 `unmount` 时又 `createRoot`；脚本是否被插入两次。
- **处理**：模块级 `root`，`unmount` 后置空；同一 name 串行；子应用不要自己 `startApp`。

### 退出后状态残留

- **现象**：回首页再进 ERP，还停留在上次的订单页（若这是入口恢复则是预期）；或登出后再登录仍看到上一个用户的页面。
- **排查**：入口是否误用指定路径；登出是否调用了 `destroyAllMicroApps`。
- **处理**：侧栏入口恢复上次路由；指定链接走 `/erp/...`。登出、租户变化必须销毁保活实例并清 `sessionStorage`。

---

## 9. 新项目接入检查清单

按实施顺序勾选。

**配置**

1. shared 增加 `name` / `basename` / `defaultPath`（业务菜单仍放在子应用内）。
2. `MICRO_APPS` 增加一条；非 Tailwind v4 不要挂 `tailwindV4ShadowCssPlugin`。
3. Shell `.env.example` 增加 `VITE_*_ENTRY`。
4. `setupMicroApps` 无需改逻辑（会自动遍历清单）。

**路由与鉴权**

5. `router.tsx` 增加 `/xxx` 重定向和 `/xxx/*` 包装组件，放在 `RequireAuth` 内（若该系统也需登录）。
6. 侧栏走入口恢复（`getMicroAppEntryHref`）；指定页面使用完整 `/xxx/path`。
7. 包装组件用 `buildMicroAppUrl` 与 `useMicroHostRouteSync`，不要手写 `/xxx` + `/xxx`。
8. `props` 只传 token / tenant / user 等显式字段。

**子应用生命周期**

9. 子应用 **不** 安装 `wujie`。
10. 实现 `__WUJIE_MOUNT` / `__WUJIE_UNMOUNT`；Vite 下调用 `__WUJIE.mount()`。
11. React 19：`unmount` 后 `root = null`。保活时官方不会二次 `UNMOUNT`。
12. 内部 Router **无** 主应用 basename；挂路由桥，监听 `MICRO_EVENTS.hostNavigate`。
13. 独立运行与嵌入都能打开。

**Vite / 部署**

14. `server.origin`、CORS、`Access-Control-Allow-Origin`。
15. 生产 `VITE_*_ENTRY` 指向真实静态 Origin。
16. Shell 注册表 `fiber: false`、`degrade: false`、`alive: true`、`sync: false`、`exec: false`（除非有明确理由改）。

**样式**

17. Tailwind v4 才在该应用的 `plugins` 里加 CSS 插件。
18. Ant Design 配 `getPopupContainer`；其他组件库用自己的挂载点。

**测试**

19. 首页 `/` 不加载该子应用。
20. 菜单进入默认页，非白屏。
21. 子应用内部切路由，地址栏 pathname 变为 `/xxx/orders`。
22. 子应用 → 首页 → 入口，恢复上次页面且 Network 不再拉整套 JS/CSS。
23. 首页指定链接能覆盖上次路由。
24. 刷新深层链接；浏览器前进后退。
25. 开发模式 Console 无 `_cacheListeners`、`prototype`、`null.protocol`。
26. 登出后再登录，看不到旧页面状态。
27. 至少抽测一种弹层（Select 或 Modal）。
