# 微前端技术实践与面试复盘

本文是对 **Neorvion 当前仓库** 里 Shell + Wujie + ERP 接入过程的复盘，用来准备前端高级岗位 / 微前端相关面试。接入步骤、配置清单见 `docs/micro-frontend-integration.md`，本文只讲「为什么这么做」和「问题是怎么查出来的」。

定位说明：

- 这是一个正在建设中的 Monorepo（当前里程碑见 `docs/architecture.md`：V2.2.1）。已落地并验证的子应用只有 ERP。
- 不要把它讲成已经在企业里完成了多系统大规模迁移。
- 白屏问题 **不是** 「Wujie 不兼容 React 19」。根因是沙箱初始化约定被破坏，以及 `wujie-react@1.0.29` 的启动队列在 StrictMode 下失效。

---

## 1. 项目背景和微前端选型

### 1.1 为什么用微前端

Neorvion 的目标是逐步把 ERP、SCM、CRM 等业务系统接到同一个登录和工作台里。这些系统：

- 可能来自不同仓库、不同技术栈（React、Vue2、Vue3 都在规划里）；
- 需要独立开发、独立部署；
- 不能要求每个业务团队都去改 Wujie 内部实现。

当前仓库已经拆成 `apps/shell`、`apps/erp`、`packages/shared`。Shell 负责登录、导航和子应用注册；ERP 负责自己的菜单和页面。这是「先把边界立住」，不是已经接完多套生产系统。

如果继续做成一个巨石 React 应用，后面接入 Vue 项目就要重写。如果做成完全独立的站点，鉴权和导航会散掉。微前端是这两者之间的折中。

### 1.2 和 iframe、qiankun、Wujie 的差别（结合本项目）

| | 传统 iframe | qiankun | Wujie 1.0.29 |
| --- | --- | --- | --- |
| JS 隔离 | 浏览器原生，最干净 | 主要靠 snapshot / Proxy，历史包袱多 | 隐藏 iframe 当 JS 沙箱 |
| CSS 隔离 | 天然隔离 | scoped CSS、shadow 可选，弹层容易漏 | 默认 Shadow DOM（`degrade: false`） |
| 接入成本 | 低，但路由、高度、通信都要自己做 | 子应用通常要改 webpack publicPath、生命周期 | 子应用只挂 `__WUJIE_MOUNT` / `__WUJIE_UNMOUNT` |
| 路由 | 父子几乎不通 | 约定较多 | `sync` + 查询参数，本项目是 `?erp=` |
| 本项目为何没选 | 要自己做 URL 同步、弹层、鉴权穿透 | 对「低侵入接现成 Vite 应用」不如 Wujie 直接 | 官方提供 iframe + Shadow 的组合，且子应用不必装 SDK |

选择 Wujie，是因为当前约束就是：**低侵入、技术栈无关、Shadow DOM 样式隔离、主应用统一管生命周期**。不是因为「社区最新」或「性能数字更好」——本项目没有做过框架间的性能对比，面试时不要编。

qiankun 不是没评估价值，而是它更依赖子应用按它的生命周期和构建约定改造。本仓库希望 ERP 继续用自己的 Vite + React Router，独立打开 `http://localhost:8016` 也能跑。

---

## 2. 架构设计

### 2.1 结构

```text
Shell（React 19 + React Router）
  setupMicroApps()  → 官方 setupApp，exec: false，不预加载
  MICRO_APPS        → 注册 name / 入口 / 插件
  /erp/*            → ErpMicroApp
                        WujieHost  按 name 串行 startApp / destroyApp
                          wujie@1.0.29
                            隐藏 iframe（JS）+ wujie-app Shadow DOM（CSS）
                              ERP 自己的 React 树
```

关键文件：

- 注册表：`apps/shell/src/micro/apps.ts`
- 启动前配置：`apps/shell/src/micro/setup.ts`
- Host：`apps/shell/src/micro/wujie-host.tsx`
- ERP 包装：`apps/shell/src/micro/ErpMicroApp.tsx`
- 子应用入口：`apps/erp/src/main.tsx`
- 通信类型：`packages/shared/src/types/bridge.ts`

### 2.2 低侵入原则具体指什么

1. **子应用不装 `wujie`。** `apps/erp/package.json` 没有这个依赖。运行时由主应用注入 `__POWERED_BY_WUJIE__`、`$wujie`、`__WUJIE`。
2. **子应用不调用 `startApp`。** 启动权在 Shell。子应用只实现 mount / unmount。
3. **兼容层留在 Host。** StrictMode 串行、卸载销毁，都在 `WujieHost`，不要求业务仓库去打 Wujie 补丁。
4. **样式特例按应用注册。** Tailwind v4 插件只出现在 ERP 那一条 `plugins`，不会变成所有子应用的默认行为。
5. **鉴权单向传递。** Shell 把 `token` / `tenantId` / `user` 放进 props；ERP 用 `getShellProps()` 读。ERP 不做 Refresh。

独立开发：`pnpm --filter @neorvion/erp dev` 走 `else { mountApp() }`。嵌入时走 Wujie 钩子。同一份代码。

---

## 3. 真实故障一：客户端路由切换白屏

### 3.1 现象（已实际遇到）

- 从首页 `/` 点侧栏进 `http://localhost:8015/erp/dashboard?erp=%2Fdashboard`，内容区白屏。
- **刷新同一地址可以出来。**
- Console 出现过：
  - `Cannot set properties of null (setting '_cacheListeners')`
  - `Cannot read properties of undefined (reading 'prototype')`
  - 另有 `null.protocol`（`getCurUrl` 一类路径上读 location）

独立打开 `http://localhost:8016/dashboard` 正常。所以不是 ERP 自己把页面写挂了。

### 3.2 相关源码（wujie@1.0.29）

**`iframeGenerator`**（`node_modules/wujie/esm/iframe.js`）

```js
var src = attrs && attrs.src;
if (!src) {
  src = getSandboxEmptyPageURL(); // blob: 空 HTML
  useObjectURL = !!src;
  if (!src) src = mainHostPath;
}
```

官方注释写得很清楚：iframe 必须禁止加载 html，防止走进主应用路由。空页用 blob：

```js
new Blob(["<!DOCTYPE html><html><head></head><body></body></html>"], { type: "text/html" })
```

如果调用方传了 `attrs.src`（哪怕是一张空白 html），**整段 blob 逻辑被跳过**。

**`initIframeDom`**（同文件）

```js
iframeWindow.__WUJIE_RAW_DOCUMENT_QUERY_SELECTOR__ = iframeWindow.Document.prototype.querySelector;
```

这里假定 `iframeWindow.Document` 已经是可用的构造器。若 iframe 还在导航、被拆掉、或 document 处于异常态，`Document` 是 `undefined`，就会报 `reading 'prototype'`。

**`stopIframeLoading`**

blob 模式下会 `document.open()` / `close()`，再进入 `initIframeDom`。走真实 `src` 时，等的是「document 对象换掉」。SPA 下主应用从 `/` 切到 `/erp/dashboard` 时，这个等待和主应用自己的 history 叠在一起，时序比刷新直开更脆。

**`patchRenderEffect`**（`esm/effect.js`）

```js
if (!degrade) {
  patchEventListener(render.head);
  patchEventListener(render.body);
}
```

**`patchEventListener`**

```js
element._cacheListeners = listenerMap;
```

`render.head` / `render.body` 来自 Shadow 里 `querySelector("head")` / `"body"`（`esm/shadow.js` 的 `_renderTemplateToShadowRoot`）。模板还没进去、或实例已销毁时，这两个是 `null`。

**`startApp` / `destroyApp`**（`esm/index.js`）

`startApp` 会 `new WuJie` → `iframeGenerator` → `importHTML` → `active`（往 Shadow 填模板）→ 执行子应用脚本。`destroyApp(id)` 直接 `sandbox.destroy()`。两个异步过程共用同一个 `name` 对应的 iframe / Shadow。并行时，一次 `initIframeDom` 还在跑，另一次已经把 iframe 拆了。

### 3.3 结论怎么划分

**已验证（改完后白屏消失，且对应代码路径对得上）：**

1. 给沙箱 iframe 设置 `attrs.src`（包括项目里一度使用的空白 html）会跳过 1.0.29 的 blob 空文档。当前 Host **不再传 `attrs.src`**。
2. 白屏发生在 **客户端路由进入**，刷新直开同一 URL 往往能过。说明问题在「运行中的主应用 history 变化 + 新建沙箱」，不是 ERP 静态资源本身坏了。
3. `_cacheListeners` 只在 `degrade === false` 时打到 shadow 的 head/body 上；head 为 null 就会炸。这与当时默认 Shadow 模式一致。

**源码支持、但单次排障时没有逐步打印证实的机制：**

- `attrs.src` 指向主应用源时，iframe 可能短暂加载主应用文档，和官方「禁止加载 html」的意图相反。
- SPA 跳转时 `history.replaceState` 与 iframe 初始化窗口的 `replaceState` 交错。

**推断（不要讲成已证实）：**

- 「React 19 改了 DOM 所以 Wujie 挂了」——没有源码或对照实验支持。生产构建关掉 StrictMode 后更稳，指向的是开发态双重挂载，不是 React 19 的 DOM API 坏了。

### 3.4 面试时怎么讲这条

先讲现象：刷新行、从首页点进去不行。再讲你读了 `iframeGenerator`，发现 `attrs.src` 会让空 iframe 变成一次真实导航。最后讲 `_cacheListeners` 是 Shadow 渲染补丁，head 为 null 说明模板或实例已经不在了。把「配置破坏了框架初始化约定」讲清楚，比抛框架名有用。

---

## 4. 真实故障二：React StrictMode 与异步生命周期竞争

### 4.1 `wujie-react@1.0.29` 实际代码

当前 `apps/shell/package.json` **只依赖** `wujie@1.0.29`，已经不用 `wujie-react`。下面依据当时读过的 `wujie-react@1.0.29` 源码（`execStartApp` / `componentDidMount`）。

`componentDidMount` 用 **`this.props.name`** 去读、写 `window.__WUJIE_QUEUE`：

```js
if (window.__WUJIE_QUEUE[this.props.name]) {
  this.startAppQueue = window.__WUJIE_QUEUE[this.props.name];
}
```

`execStartApp` 却把队列写到 **`this.name`**：

```js
this.startAppQueue = this.startAppQueue.then(this.startApp);
window.__WUJIE_QUEUE[this.name] = this.startAppQueue;
```

这是 class 组件，没有把 `props.name` 赋给 `this.name`。`this.name` 一直是 `undefined`。于是：

- 读队列的键是 `'erp'`
- 写下一次任务的键是 `undefined`

两次挂载对不上同一条 Promise 链。

另外，该版本 **没有 `componentWillUnmount` 去 `destroyApp`**。`startApp` 的返回值赋给 `this.destroy`，但卸载时没有调用。离开路由时沙箱是否拆掉，并不由这个 React 封装保证。

### 4.2 为什么 StrictMode 会放大它

Shell 入口 `apps/shell/src/main.tsx` 包了 `<StrictMode>`。开发态会：挂载 → 立刻卸载 → 再挂载。

对 Wujie 来说，`startApp('erp')` 不是「setState」那种可重入更新，而是创建 iframe、拉 HTML、改 Document、填 Shadow。两个实例各调一次 `startApp`，又对不齐队列，就会并行。

### 4.3 时间线

**错误（并行）：**

```text
实例 A  mount → startApp(erp) 开始建 iframe
实例 A  unmount → （wujie-react 未必 destroy）
实例 B  mount → startApp(erp) 又建一份 / 操作同一 id
        ── 两段 initIframeDom / patchRenderEffect 交错
        ── Document.prototype 或 head 变成 undefined / null
```

**当前 Host 的顺序（`wujie-host.tsx` 的 `enqueue`）：**

```text
startApp(1) 若 effect 已被取消 → 跳过，或 start 完立刻 destroyApp
  → destroyApp(1)
  → startApp(2)
```

`active` 标志在 cleanup 里置 false。即便 `startApp(1)` 已经进队，执行时发现不该再挂，就不会把过期实例留在页面上。

同一 `name` 必须串行，是因为 Wujie 用 `name` 当沙箱主键（`getWujieById`）。这和「React 组件可以同时存在两个 function 闭包」不是同一类资源。

### 4.4 为什么由 Shell Host 统一管，而不是改每个子应用

- 队列键写错发生在 **主应用使用的封装层**，ERP 里没有 `startApp`。
- 若要求每个 Vue / React 子应用自己包一层「正确的队列」，低侵入就失败了，后面接 SCM 还得再踩一次。
- Host 只调官方 `setupApp` / `startApp` / `destroyApp`，不 fork Wujie。兼容成本留在一处。

安装 `wujie` 核心包是合理的：本来真正干活的就是它，`wujie-react` 只是一层有缺陷的 UI 封装。继续留着未使用的 `wujie-react` 只会让人误以为官方组件仍是入口。

---

## 5. 真实故障三：Shadow DOM 与 Tailwind v4

### 5.1 `degrade=true` 为什么能「绕过」一部分白屏

`patchRenderEffect` 在 `degrade === true` 时 **不** 调 `patchEventListener`。渲染走可见 iframe（`renderTemplateToIframe`），`patchRenderEffect(..., true)`。于是 `_cacheListeners` 这条路径不会碰到 null 的 shadow head。

这只能说明「默认模式的那次 DOM patch 没跑」，**不能**说明降级后沙箱初始化、路由同步、弹层、主题变量都正确。把 `degrade: true` 当正式方案，等于放弃 Shadow 隔离，主子样式重新可能互相污染。本项目最终保持 `degrade: false`。

### 5.2 `:root` 和 `:host`

- `:root` 是文档根（html）。普通页面里 Tailwind v4 主题变量写在这里。
- Shadow 树里，子应用 CSS 进的是 `wujie-app` 的 shadowRoot。`:root` 匹配不到这棵树内部的「根」。
- `:host` 匹配自定义元素自身，变量才能在影子树里继承。

Wujie 自己的 `getPatchStyleElements`（`esm/shadow.js`）会把已解析 stylesheet 里的 `:root` 规则抄一份成 `:host`。`patchCssRules` 在 `degrade` 时直接 return。Tailwind v4 生成量大，构建期用 cssLoader 改选择器更稳，所以 ERP 额外挂了 `tailwindV4ShadowCssPlugin`（`apps/shell/src/micro/css-plugins.ts`）。

### 5.3 为什么不能无条件 `replaceAll(':root', ':host')`

- 可能改到 `url()`、自定义属性名里偶然出现的文本。
- **更重要：降级 iframe 里 `:root` 才是对的。** 无条件替换会让 iframe 模式主题失效。插件用选择器边界的正则，并且 **只写在 ERP 的 `MICRO_APPS.plugins`**。

### 5.4 Ant Design 弹层

`document.body` 在嵌入后往往是 **主应用 body**，或者至少不在影子树里。Select / Modal / Drawer 会飞到主页面。ERP 在 `apps/erp/src/app/providers.tsx` 把 `getPopupContainer` 指到影子树内 `#root`（实现见 `apps/erp/src/lib/runtime.ts`）。这是 Antd 子应用自己的事，不是 Host 的全局配置。

Dashboard 上没有把所有弹层点完，面试时要承认这点。

---

## 6. 修复方案与权衡

| 方案 | 做法 | 优点 | 代价 |
| --- | --- | --- | --- |
| 官方 `WujieReact` + 补丁 | fork 或包装，修 `this.name`、补 unmount | 表面仍用官方组件 | 要跟踪上游；子应用增多时补丁语义容易散 |
| **Wujie 核心 API + 自定义 Host（当前）** | Shell 依赖 `wujie@1.0.29`，`WujieHost` 串行 + destroy | 兼容集中；子应用零 SDK；API 面小 | 要自己处理 StrictMode 取消和 loadError |
| `degrade=true` | 可见 iframe | 能避开 shadow head 的 patch | 失去默认 CSS 隔离；`:root` 插件语义反了；不是目标架构 |

选择 Host 的技术原因：真正的沙箱从来都在 `wujie` 包里；出问题的是 React 封装的队列键和卸载。维护成本是多维护约一百行 Host，而不是给每个业务仓库发补丁。风险是 Wujie 大版本改 `startApp` 签名时 Host 要跟着改——这比默默依赖一个有 `this.name` 缺陷的封装更可控。

移除未使用的 `wujie-react`：避免 `package.json` 暗示「渲染请用这个组件」，也避免 lockfile 里两套入口让后人改错文件。

---

## 7. 实际验证结果和剩余风险

以下是架构收口后 **实际跑过** 的，不要扩写成「全量回归」。

**已做：**

- 首页 `/` 不创建 ERP 沙箱，再进入 `/erp/dashboard`。
- ERP 回到首页，再进 ERP；`alive: false` 下打开的是 dashboard，不是上次的订单页。
- ERP 内跳到订单，地址栏出现 `?erp=%2Forders`。
- 刷新 `/erp/dashboard?erp=%2Fdashboard`。
- 直开 `/erp/orders` 深层链接。
- 仍为 Shadow DOM（`degrade: false`）。
- 开发态未再看到当初那组 `_cacheListeners` / `Document.prototype` / `null.protocol`。

**未完整验证：**

- 退出登录再登录整条链路（这次收口没重跑）。
- Ant Design Select、Modal、Drawer 的全部交互。
- 多个子应用同时存在、快速来回切的压力（仓库里也还没有第二个子应用）。

面试被问「测了吗」时，把上面两组分开说，比说「已经很稳定」更像做过事的人。

---

## 8. 面试表达

下面按口语写，大约七年前端经验、讲自己做过的接入，不要用「赋能」「中台闭环」这类词。

### 30 秒项目介绍

我最近在做一个 ERP 方向的 Monorepo。主应用是 React 19 的 Shell，负责登录和工作台；业务先接了一个 React 的 ERP 子应用，用 Wujie 嵌进去。默认 Shadow DOM，子应用不用装 Wujie。后面还要接 SCM、CRM，可能是 Vue，所以主应用这边把注册、启动、销毁收口了，尽量不让每个业务仓库去碰沙箱细节。

### 2 分钟微前端架构介绍

主应用有一份子应用清单，现在只有 ERP：名字、挂载前缀 `/erp`、入口地址、要不要保活、要不要挂 Tailwind 的 CSS 插件。启动前 `setupApp`，但 `exec: false`，首页不会预加载 ERP。用户进 `/erp/*` 才渲染一个很薄的 Host，里面调官方 `startApp`。离开就 `destroyApp`，现在 `alive` 是 false，避免菜单点 dashboard 却还停在订单页。

子应用还是自己的 Vite 和 React Router，路径是 `/dashboard`、`/orders`，没有 `/erp` 前缀。主应用用 `buildMicroAppUrl` 把 `/erp/dashboard` 剥成子应用的 `/dashboard`。token 和租户通过 Wujie props 传，ERP 不读主应用的 store，也不做 refresh。样式上 Tailwind 的 `:root` 问题只给 ERP 挂插件，避免将来 Vue 应用被误伤。

### 3～5 分钟白屏排查案例

现象是从首页点进 ERP 白屏，刷新就好。独立打开 ERP 也正常。所以我没先去改业务页面。

Console 里有给 null 设 `_cacheListeners`，还有 `Document.prototype` 读不到。我去 1.0.29 源码里对了：`_cacheListeners` 是默认模式下给 Shadow 的 head、body 打事件补丁；`Document.prototype` 是 iframe 初始化时假定 `iframeWindow.Document` 已经在。说明沙箱 DOM 没准备好，或者实例被拆掉了还在 patch。

然后看到 `iframeGenerator`：一旦传了 `attrs.src`，它就不用 blob 空页面。官方注释说这个 iframe 不能去加载真正的 html，否则会进主应用路由。我们当时给过空白页地址，等于自己破坏了这个约定。客户端跳转时主应用 history 已经在变，比刷新直开更容易撞上。

第二件事是 React 18/19 开发态 StrictMode 会连挂两次。当时用的 `wujie-react` 把队列写到 `this.name`，componentDidMount 却按 `this.props.name` 去取，键对不上，两次 `startApp` 并行。Wujie 按 name 只有一份沙箱，并行就会把 Document 和 shadow head 打坏。

最后没有在业务里打补丁，也没有靠 `degrade=true` 交差。主应用自己写了 Host：按 name 排队，effect 取消就 destroy，并且不再设 `attrs.src`。子应用仍然只提供 mount、unmount。这样后面接 Vue 不用再修一遍。

### 为什么不用 wujie-react

不是嫌官方组件「不够高级」。1.0.29 这层封装把启动队列写错键，而且看不到按 React 卸载去 destroy。真正创建沙箱的是 `wujie` 的 `startApp`。Shell 直接调核心 API，用几十行把 StrictMode 和销毁收住，比在业务里补丁官方组件更干净。现在依赖里只留 `wujie`，避免后人继续去包 `<WujieReact>`。

### 为什么选择 Wujie

我们要接的是现成 Vite 应用，最好独立开发时零改造。Wujie 用隐藏 iframe 做 JS 隔离、Shadow DOM 做 CSS 隔离，子应用约定就是两个生命周期函数。iframe 方案隔离更好但路由和高度都要自己做；qiankun 对构建和生命周期侵入更多。当前阶段 Wujie 更贴「低侵入」。没有做性能跑分，不拿 QPS 说事。

### Shadow DOM 样式隔离

默认 `degrade: false`，子应用进 `wujie-app` 的影子树，主应用 CSS 进不去，子应用 CSS 也尽量不出来。Tailwind v4 变量写在 `:root` 上，影子树里要改成 `:host` 才会生效。我们没做全局字符串替换，只给 ERP 注册 cssLoader，免得 Vue 或者哪天打开降级 iframe 时主题挂掉。Antd 弹层再单独把 `getPopupContainer` 指到影子树里的 `#root`。

### StrictMode 为什么会暴露生命周期问题

StrictMode 在开发环境故意 mount、cleanup、再 mount，用来抓「订阅了却不退」的 effect。对普通 setState 没问题。对 Wujie 这种「按 name 创建全局沙箱」的异步 API，两次 start 如果没有排队、中间又不 destroy，就会操作同一份 iframe。生产构建没有双重挂载，所以有人会误以为「只有开发坏」；根子是异步生命周期没按实例取消，StrictMode 只是把它提前暴露了。

### alive=true / false 怎么选

`true` 是离开页面实例还在，再进来恢复内存状态，适合切 tab 不想丢表单。`false` 是离开就拆沙箱，再进按新 url 加载。我们菜单写死进 `/erp/dashboard`，如果保活，用户上次停在订单页，再点「ERP 业务」会对不上菜单。白屏修掉之后也不需要用保活掩盖启动竞争，所以现在用 `false`。以后若产品要「切走再回来还在填」，再单独开，并接受和菜单默认页冲突。

### 旧项目怎么低侵入迁进来

主应用加一条注册：name、basename、入口 env、要不要 CSS 插件。Router 加 `/xxx/*`。子应用不装 wujie，入口判断 `__POWERED_BY_WUJIE__`，挂 mount/unmount，Vite 再调 `__WUJIE.mount()`。内部路由不要带主应用前缀。token 走 props。Vite 配 `server.origin` 和 CORS。这些在接入文档里是检查清单，业务代码不用理解 iframe 实现。

---

## 9. 深挖追问（15+）

**1. Wujie 的 JS 隔离具体是怎么做的？**

隐藏 iframe 与主应用同源，但有自己的 `window` / `document`。子应用脚本插到 iframe 里跑，通过 `patchIframeVariable`、对 history、事件、节点的 patch，把对 `document` 的操作映射到 Shadow 或降级 iframe。不是 Proxy 一遍全局对象那么简单，所以 iframe 自己的 Document 必须先初始化好。

**2. 为什么还要 Shadow DOM？iframe 不是已经隔离 CSS 了吗？**

默认模式下 **可见 UI 不在那个隐藏 iframe 里**，而在主文档的 `wujie-app` 影子树里。隐藏 iframe 负责 JS；Shadow 负责把 DOM 和 CSS 接到主页面指定容器。`degrade: true` 才把 DOM 画在可见 iframe 里。

**3. 同源 iframe 会不会直接读到主应用 Cookie？**

会共享 Cookie 存储。本项目鉴权设计是 Shell 管 Refresh Cookie，ERP 只用 props 里的 Access Token（见 `docs/auth.md`）。不能假设 iframe 沙箱等于鉴权沙箱。

**4. `fiber: false` 是什么？**

Wujie 可以把外部脚本拆成可中断的任务。Vite 开发是 ESM，执行时机和「框架以为脚本插完就 mount」不一致。本项目在注册表里对 ERP 关 fiber，入口再主动 `__WUJIE.mount()`。没在别的应用上对比过开关差异，只解释当前选择。

**5. `exec: false` 和预加载？**

`setupApp` 只缓存配置。`exec: false` 表示不要预执行。首页不调用 `preloadApp`，避免一打开工作台就拉 ERP。

**6. `sync` 的查询参数名为什么是 `erp`？**

它等于子应用 `name`。`prefix: { erp: '/erp' }` 做短路径替换。子应用真实路径是 `/dashboard`，所以常见形态是 `?erp=%2Fdashboard`，不是 `?erp=/erp/dashboard`。

**7. 如何避免 `/erp/erp`？**

剥前缀只发生在 Shell 的 `buildMicroAppUrl`。ERP 的 `BrowserRouter` 没有 `basename="/erp"`。两边都加前缀才会重复。

**8. 主应用 pathname 还是 `/erp/dashboard`，但 `?erp=%2Forders`，以谁为准？**

侧栏从 dashboard 进入再在子应用内跳转时，会出现这种分裂。Wujie 用查询参数恢复子应用路由；`buildMicroAppUrl` 仍看 Shell 的 pathname。刷新 `/erp/dashboard?erp=%2Forders` 时，同步参数优先（Wujie `isMatchSyncQueryById`）。产品上若要地址栏 pathname 也变成 `/erp/orders`，要额外做一层主应用 navigate，当前没做。

**9. 子应用怎么给主应用发消息？**

Wujie 提供 `bus`。shared 里预留了 `SHELL_EVENTS`（`tenantChanged`、`navigate`），当前 ERP 主路径仍是 props 下行。不要说已经做了完整跨应用事件总线。

**10. 资源 404 和 `server.origin`？**

Shell 在 8015 跨源 fetch 8016 的 HTML。相对路径 `/src/main.tsx` 若按主应用 origin 解析就会 404。ERP 的 Vite `server.origin = 'http://localhost:8016'` 把资源写成绝对地址。CORS 头让主应用能拉脚本。

**11. 部署上主子应用如何拆？**

开发两端口。生产用 `VITE_ERP_ENTRY` 指向 ERP 静态 Origin。当前 `nginx/nginx.conf` 只把 `/` 转到 Shell 8015，**没有**现成的 ERP location。面试不要说「生产网关已经按子应用拆好」。

**12. 保活对内存和路由的影响？**

`alive: true` 不拆 iframe，再进入快，但 JS 堆、定时器还在。多子应用同时保活会叠内存。路由上可能和「菜单默认页」冲突。当前单子应用 + `alive: false`，没有做内存采样。

**13. 快速来回点菜单会怎样？**

Host 把同一 name 的 start/destroy 串成 Promise 链。快速进出不会并行 init，但会排队，可能感到稍慢。这是正确性优先。多应用并发压力没测。

**14. 如何排查「独立运行好、嵌入白屏」？**

看脚本 URL 是否打到 8015；看 shadow 里有没有 `#root`；看有没有生命周期报错；看是否误设 `attrs.src`；看 StrictMode 下有没有两次 start。不要一上来升级 React。

**15. 自定义 Host 算不算重写 Wujie？**

不算。没有实现沙箱、没有复制 `importHTML`。只是调用方把「何时 start / destroy、同一 name 如何排队」写清楚。相当于不用有 bug 的 React 封装。

**16. Vue 子应用和 React 最大差别？**

挂载 API 不同（`createApp` / `$mount` vs `createRoot`）。没有 Tailwind v4 就不要挂那个 CSS 插件。弹层用各组件库自己的 teleport。本仓库 **没有 Vue 子应用，模板未验证**。

**17. 为什么 Access Token 放 props 而不是让子应用自己登录？**

登录和 Refresh 收口在 Shell，减少多个子应用各自存 Cookie、抢着 refresh 的问题。ERP 拿到的是当前内存里的 token。代价是 props 更新时机要随 Host 的 `startApp`；token 刷新后子应用是否立即拿到，取决于是否重新 start 或另走 bus。当前 `alive: false` 每次进入会带上最新 props。完整「登出再登录」未在最近一轮重测。

**18. Shadow 里 `document.querySelector` 为什么要 patch？**

子应用代码以为自己在完整文档里。Wujie 把查询、创建节点指到影子树 / 沙箱 document，否则会对着主应用 DOM 插节点。这也是 `initIframeDom` 必须先拿到 `Document.prototype` 的原因。

---

## 10. 简历项目亮点

写自己的练习 / 进行中的项目时，用「建设中」「已完成能力 / 规划中」分开，不要写用户量、团队人数、性能提升百分比。

**示例 1**

负责 Neorvion Monorepo 的 Shell 微前端接入：基于 `wujie@1.0.29` 核心 API 实现自定义 Host，统一子应用注册、启动与销毁；ERP 子应用不依赖 Wujie SDK，保持独立 Vite 开发与部署。

**示例 2**

排查并修复「首页客户端路由进入 ERP 白屏、刷新正常」：结合 Wujie 沙箱 `iframeGenerator` / `initIframeDom` / `patchRenderEffect` 源码，定位空 iframe `src` 破坏初始化，以及 `wujie-react` 启动队列在 React StrictMode 下并行 `startApp` 的问题；最终将兼容逻辑收口在主应用，而不是下放到业务仓库。

**示例 3**

处理 Shadow DOM 下 Tailwind CSS v4 主题变量与 Ant Design 弹层容器问题：CSS 插件按子应用注册，避免把 ERP 专用规则扩散到后续 Vue 等应用。已验证首页进入、往返、内部路由与深层链接刷新；完整登出登录、弹层全量和多应用压测仍待补。

---

## 和接入文档的分工

| 文档 | 用途 |
| --- | --- |
| `docs/micro-frontend-integration.md` | 怎么接一个新应用（步骤、配置、FAQ、清单） |
| 本文 | 为什么这样接、白屏怎么查、面试怎么讲 |

不要在面试里背注册表字段；被问到「怎么接」时再落到接入文档的检查清单。
