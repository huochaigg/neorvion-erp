# 架构说明

当前里程碑：V2.1 用户认证。

## 目标

用模块化单体支撑后续采购、库存、订单、物流和 AI Agent，而不是一上来拆微服务。

## 前端

### 应用边界

- `apps/shell`：统一登录、注册、认证状态、顶部导航、微前端注册。
- `apps/erp`：业务菜单、业务页面、业务客户端状态。可独立启动，便于调试。
- `packages/shared`：路由常量、API 响应类型、Wujie 通信类型、Query Key。

主应用不得读取 ERP 内部 store；ERP 只能通过 `window.$wujie.props` 与 `bus` 接收主应用显式传入的状态。

### 路由

- 主应用：`/` 工作台，`/erp/*` 挂载子应用。主应用根路径不会打开 ERP。
- 子应用独立运行在 `http://localhost:8016/`，内部路径为 `/dashboard`、`/products` 等，**没有** `/erp` 前缀。
- 主应用浏览器地址是 `/erp/dashboard`；无界会把它映射成子应用的 `/dashboard`。刷新后仍由主应用按 `/erp/*` 加载子应用。

### 无界

- 子应用名称固定为 `erp`。
- Vite 子应用关闭 fiber，并在入口调用 `window.__WUJIE.mount()`。
- 开发服务器开启 CORS，并用 `server.origin` 输出绝对资源地址。
- CSS Loader 把 `:root` 映射为 `:host`，减少 Tailwind 主题变量泄漏。
- Ant Design Portal 组件通过 `ConfigProvider.getPopupContainer` 挂到当前应用 `#root`。

### 状态

- Zustand：仅客户端 UI 与 Access Token（内存）。用户资料走 React Query。
- React Query：服务端数据。业务 Query Key 必须包含 `tenantId`；当前用户使用 `current-user`。
- 租户切换时取消未完成请求并 `queryClient.clear()`。V2.2 接入真实租户后生效。

### 样式

- 优先 Tailwind CSS 4（`@tailwindcss/vite` + `@import "tailwindcss"`）。
- 复杂品牌/页头使用 `*.module.scss`。
- 全局 CSS 只放 reset、字体和主题变量。
- Ant Design 主题只通过 ConfigProvider Token 定制，不使用 `!important` 覆盖。

## 后端

分层：

1. API Router：HTTP、校验、依赖注入。
2. Service：业务规则、事务、状态机。后续库存事务在这里 `session.begin()`。
3. Repository：查询与持久化，禁止 commit。
4. Model / Schema：ORM 与 Pydantic。
5. Core：配置、安全、异常、日志、租户 ContextVar。

认证：

- `get_current_user()` 统一解析 Access Token。
- Refresh Token 会话写在 Redis，便于注销。
- 后续 V2.2 增加 `get_current_tenant()` / `get_tenant_context()`，不要把租户 ID 塞进 `users` 表。

AI 与异步：

- `app/agents`：后续 OpenAI Agents SDK，Tool 调 Service。
- `app/tasks`：后续 Celery。

## 端口

| 服务 | 端口 |
| --- | --- |
| Shell | 8015 |
| ERP | 8016 |
| FastAPI | 8011 |
| MySQL | 3306 |
| Redis | 6379 |
| Nginx（可选） | 8080 |
