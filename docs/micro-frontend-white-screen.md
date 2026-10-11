# 微前端隔夜白屏

本文说明这一次故障：ERP 子应用停在某个页面过一夜，第二天切回浏览器标签，内容区白屏；反复离开再进入 ERP 仍然白屏；只有手动刷新整页才恢复。

这和「从首页点进 ERP 白屏、刷新就好」不是同一件事。后者是沙箱初始化被破坏，见 `docs/micro-frontend-interview.md`。本文的页面本来已经画出来过，是保活实例在后台失效之后被原样挂了回来。

相关代码：

| 路径 | 职责 |
| --- | --- |
| `apps/shell/src/micro/wujie-host.tsx` | 切回页面时如果沙箱已空，销毁后重新挂载 |
| `apps/shell/src/micro/sandbox-health.ts` | 判断隐藏 iframe 是否已被浏览器清掉，并等旧实例拆完 |
| `apps/shell/src/api/client.ts` | 刷新 Access Token 后写回还活着的沙箱，避免为此重启子应用 |

---

## 1. 现象

1. 登录后进入 `/erp/*`，页面正常。
2. 浏览器标签留在这个页面上，电脑放一夜（或标签被切到后台很久）。
3. 第二天切回该标签：Shell 的顶栏、侧栏还在，ERP 内容区空白。
4. 切到工作台再切回 ERP，或在子应用之间来回进入，内容区仍然空白。
5. 按浏览器刷新，页面恢复，而且是重新加载了一套子应用脚本。

Console 里通常没有新的脚本报错。Network 里也不会再去拉 ERP 的 JS/CSS。看起来像「应用还在，只是什么都没画」。

---

## 2. 结论

ERP 开着无界保活（`alive: true`）。保活把两份东西留在内存里：

- 隐藏的 iframe，里面跑子应用的 JavaScript。
- `<wujie-app>` 的 Shadow DOM，里面是 ERP 的 React 树。

页面在后台放久了，Chrome 会回收那个隐藏 iframe，或把 Shadow 里的 React 树清掉。无界自己的缓存还在，并且带着「脚本已经执行过」（`execFlag`）和「Shadow 还在」（`shadowRoot`）这两个标记。

再次进入 ERP 时，`startApp` 看到缓存还在，就走 `sandbox.active()`：把那块已经空掉的 Shadow 挂回容器，然后直接返回。它不会重新执行 `__WUJIE_MOUNT`，也不会再跑 React。所以切标签、切子应用都只是在反复挂同一块空白。

整页刷新会丢掉 `window` 上的无界缓存，下一次 `startApp` 才会新建沙箱、重新拉脚本、重新 `createRoot`。

Access Token 隔夜也会过期。那是伴随问题：接口会 401，但白屏本身不是「没登录」。登录页也是子应用画出来的；沙箱是空的时候，连登录页都不会出现。

---

## 3. 保活实例长什么样

无界 1.0.29，当前 ERP 的启动参数是 `alive: true`、`degrade: false`、`fiber: false`、`sync: false`。

```text
Shell 页面
  ├── 顶栏 / 侧栏（主应用 React，不受沙箱影响）
  ├── 隐藏 iframe[name="erp"]
  │     └── JS 沙箱
  │           window.__POWERED_BY_WUJIE__
  │           window.$wujie === sandbox.provide
  │           window.__WUJIE.shadowRoot 指向下面的 Shadow
  └── <wujie-app data-wujie-id="erp">
        └── Shadow DOM
              └── #root
                    └── ERP 的 React 树（真正看见的页面）
```

`__POWERED_BY_WUJIE__` 是在沙箱 `start()` 里写上的，不是创建 iframe 时就有。子应用每次发请求都从 `window.$wujie.props.token` 读当前 token，不读 Shell 的 Zustand。

离开 `/erp/*` 时，`WujieHost` 卸载，但 `alive: true` **不**调用 `destroyApp`。`<wujie-app>` 离开文档后，无界只做 `deactivated`：隐藏宿主，React 树还留在那份 Shadow 里。沙箱还在时，再进入走 `active()`，页面状态还在。没有按停留时长拆实例。

---

## 4. 浏览器在后台做了什么

隐藏 iframe 不属于当前视口。标签切走、窗口最小化、笔记本休眠之后，Chrome 可以：

- 丢弃隐藏 iframe 的文档，换上一份空白文档。这时 `iframe` 节点还在，但 `contentWindow.__POWERED_BY_WUJIE__` 没了，`$wujie`、React、定时器也没了。
- 在内存紧张时清掉 Shadow 里已经画出来的节点，`#root` 变成空的，而外层 `wujie-app` 还在。
- 对进入往返缓存（bfcache）的页面，恢复时文档是冻结前的快照，脚本不会重跑。

无界的 `idToSandboxMap` 存在主页面的 `window` 上。主页面没刷新，这份 Map 就还认为 ERP 沙箱活着。浏览器清掉的是 iframe 内部文档，不是这条缓存。

所以「切回标签」这个动作本身不会创建新沙箱。它只触发 `visibilitychange`。修复前，这个事件什么都不做，空实例继续被复用。

---

## 5. 为什么 `active()` 救不回来

无界 `startApp` 对同一个 `name` 的处理可以概括成：

1. 缓存里已经有沙箱，并且 `shadowRoot`、`execFlag` 都还在。
2. 于是调用 `active()`：把已有的 `<wujie-app>` 插回 Host 的容器，派发 `activated`。
3. 函数返回。不重新插入脚本，不调用 `__WUJIE_MOUNT`。

这在沙箱健康时是对的，切走再回来才快。沙箱已经被浏览器清空时，这两个标记仍可能是真的，`active()` 就会把空白 Shadow 挂回来。

子应用侧没有机会自救。`location.reload()` 在无界代理里是空操作，子应用里写刷新也打不中真正的浏览器刷新。

---

## 6. 为什么反复切换子应用也没用

「离开 ERP 再进来」在修复前的路径是：

1. Host 卸载，保活分支直接 return，不 `destroyApp`。
2. 再次进入，新的 Host `startApp`。
3. 命中第 5 节的 `active()`，挂回同一份空实例。

来回切只是重复第 3 步。只要主页面没刷新，无界缓存就不会自己失效。

---

## 7. 为什么只有整页刷新有效

整页刷新会：

- 清掉 `window.__WUJIE_INJECT.idToSandboxMap`。
- 清掉隐藏 iframe 和 `<wujie-app>`。
- Shell 重新登录态引导，再 `setupApp` + `startApp`。
- 无界新建 iframe，重新请求 ERP 的 HTML/JS，执行 `__WUJIE.mount()`，React 重新 `createRoot`。

所以刷新能好，不能说明「子应用代码偶发没跑起来」。它只说明旧的保活实例不能用了，新实例可以。

---

## 8. Token 过期是怎么叠上去的

Shell 持有 Refresh Cookie。ERP 自己不调用 `/auth/refresh`，请求都带 `props.token`。

修复前，Access Token 默认 30 分钟（`backend/.env` 的 `JWT_ACCESS_EXPIRE_MINUTES`）。仓库根目录 `.env` 里的 `JWT_EXPIRE_MINUTES` 后端不读。隔夜之后：

1. 内存里的 access token 已过期。
2. 子应用或 Shell 请求先 401，Shell 用 Refresh Cookie 换新 token。
3. 若这次换 token 导致 Host 的 `props` 变化，而 `startApp` 的 effect 又依赖 `props`，就会对**那份已经空掉的保活实例**再执行一次 `startApp`。
4. `destroyApp` 是异步的，而且不返回 Promise。旧实例还没从缓存删掉时，新的 `startApp` 又走 `active()`，空页面继续留着。
5. 更糟的一种情况：刷新 token 改变了 `props`，effect 重入，上一次任务在打出「重新挂载」之后、调用 `destroyApp` 之前被 generation 取消。下一次同样如此。页面会一直白，Console 里反复出现重建日志，最后 Refresh 次数耗尽，人被送回登录页。

因此 token 刷新必须写进当前沙箱的 `$wujie.props`，不能靠重启 `startApp`。只有确定沙箱已经死了，才销毁重挂，并且要等旧 iframe 和缓存条目都消失之后再 `startApp`。

---

## 9. 修复在做什么

### 9.1 什么时候重建

只看沙箱是不是已经空了，不看在后台待了多久。

| 条件 | 行为 |
| --- | --- |
| iframe 还在，但 `__POWERED_BY_WUJIE__` 没了，或读 `contentWindow` 抛错 | 浏览器已把隐藏文档清掉，切回标签或再次进入时重新挂载 |
| Shadow 里的 `#root` 曾经有过子节点，现在空了 | 内容被清掉，同样重新挂载 |
| 从往返缓存恢复（`pageshow.persisted`）且上面两条成立 | 同样重新挂载 |
| 还没有沙箱，或沙箱里的页面还在 | 不拆。健康实例继续 `active()` |

「`#root` 为空」不能一出现就当死亡。React 18 的 `createRoot().render` 是异步的，刚 `mount` 完根节点经常还是空的。代码用 `sawContent` 记住这个名字曾经画出过内容，只有「先有内容、后来没了」才算失效。

探测读的是 `iframe.contentWindow.__WUJIE.shadowRoot`。不能用主文档的 `querySelector('wujie-app')`：保活失活时宿主节点会离开文档，这时查不到不等于沙箱死了。那样的话，正常离开再进入也会被拆掉。

### 9.2 为什么要等旧实例拆完

`destroyApp` 不返回 Promise。若 iframe 还在、缓存里还有 `execFlag`，紧接着的 `startApp` 会再次 `active()` 并返回，重建等于没做。

`releaseSandbox` 最多等 500ms，直到 iframe 和 `idToSandboxMap` 条目都没了。超时则自己摘掉 iframe、丢掉缓存条目。无界 1.0.29 的 `deleteWujieById` 会把 `setupApp` 注册的 prefix、plugins 一起删掉，所以下一次启动前要再调 `setupMicroApp(name)`。

重建前先 `prepareRestart`，也就是 `refreshSessionFromShell`。会话已经失效时，这里失败，调用方会去登录页，不再挂一个带着过期 token 的新实例。

### 9.3 Token 怎么进到子应用

`WujieHost` 启动 effect 只依赖 `bootId` 和 `name`，不依赖 `props`。Access Token 更新时：

- `useAuthStore.subscribe` 和刷新成功的回调调用 `syncTokenToAliveSandboxes`。
- Host 另有一个 effect，把最新 `props` 写到 `__WUJIE.provide.props`。

子应用读的 `$wujie` 就是 `sandbox.provide`，所以下一次请求能拿到新 token，页面不用拆。

### 9.4 不要做的探测

不要在隐藏 iframe 的 `load` 上判断「`__POWERED_BY_WUJIE__` 还是 false，所以要重建」。无界创建 iframe 时这个标记尚未写上，`load` 会在初始化过程中触发，结果是无限 `setBootId`。

---

## 10. 正常逻辑

保活没有过期时间。Access Token 仍由 `JWT_ACCESS_EXPIRE_MINUTES` 决定，默认 30 分钟。调试时用过的 30 秒保活窗口和 30 秒 token 都已撤掉。

要在当天看重建是否生效，在已经画出 ERP 的页面上把沙箱标成失效，再切走切回：

```js
(() => {
  const iframe = document.querySelector('iframe[name="erp"]');
  const win = iframe?.contentWindow;
  const root = win?.__WUJIE?.shadowRoot?.querySelector('#root');
  if (win) win.__POWERED_BY_WUJIE__ = false;
  if (root) root.replaceChildren();
})()
```

切到工作台再回到 ERP，或切到别的浏览器标签再切回来。Console 应有一条 `[erp-micro] 保活沙箱已被浏览器清空，重新挂载`，内容恢复。沙箱还健康时离开再进入，应还是同一个 `iframe[name="erp"]`，且没有这条日志。

---

## 11. 怎么确认是这个问题

在白屏的那一页，于 Shell 的 DevTools Console 执行：

```js
(() => {
  const iframe = document.querySelector('iframe[name="erp"]');
  const win = iframe?.contentWindow;
  const root = win?.__WUJIE?.shadowRoot?.querySelector('#root');
  return {
    iframe: Boolean(iframe),
    powered: Boolean(win?.__POWERED_BY_WUJIE__),
    rootChildren: root ? root.childElementCount : null,
  };
})()
```

符合本文的结果是下面之一：

- `iframe: true`，`powered: false`：iframe 还在，内部文档已经被浏览器换掉。
- `iframe: true`，`powered: true`，`rootChildren: 0`：JS 沙箱还在，但已经画出过的 React 树空了。

然后刷新整页，同一段代码变成 `powered: true` 且 `rootChildren > 0`。这就和「资源 404、没调 `__WUJIE.mount()`、StrictMode 并行 `startApp`」区分开了。那些问题在第一次进入时就会白，刷新往往也白，或者 Console / Network 里有明确报错。

---

## 12. 和另一类白屏的对照

| | 隔夜 / 切回标签白屏（本文） | 从首页第一次点进来白屏 |
| --- | --- | --- |
| 发生时机 | 页面已经正常显示过，后台放久后再看 | 客户端路由第一次进入 `/erp/*` |
| 刷新 | 刷新就好 | 直开 URL 或刷新往往也好 |
| 实例 | 无界认为实例还在，`active()` 挂回空壳 | 新建沙箱时初始化被破坏 |
| 典型原因 | 隐藏 iframe 或 Shadow 内容被浏览器清掉，缓存未失效 | 空 iframe `src`、`wujie-react` 队列在 StrictMode 下并行 `startApp` |
| 文档 | 本文 | `docs/micro-frontend-interview.md` |
