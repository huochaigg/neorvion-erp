# 开发说明

当前定义：Neorvion ERP Core V1（V15 收口）。有效状态见 `docs/current-state.md`。

## 前置

- Node.js 22+
- pnpm 12+
- Python 3.12
- uv
- Docker Desktop（推荐，用于 MySQL / Redis）

## 日常命令

安装前端依赖：

```bash
pnpm install
```

同时启动主应用、ERP 与 Knowledge：

```bash
pnpm dev
```

只启动 Knowledge 微前端：

```bash
pnpm dev:knowledge
```

安装并启动后端：

```bash
cd services/erp
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8011
```

数据库迁移：

```bash
cd services/erp
uv run alembic current
uv run alembic upgrade head
uv run python -m app.scripts.seed_permissions
# 演示数据（需 DEMO_EMAIL / DEMO_PASSWORD，幂等，不在启动时自动执行）
uv run python -m app.scripts.seed_demo
uv run alembic revision --autogenerate -m "your message"
```

M1 的初始迁移为空。V2.1 增加 `users` 表，执行：

```bash
cd services/erp
uv run alembic upgrade head
```

生成本地 RSA 密钥（私钥不会提交到 Git）：

```bash
cd services/erp
uv run python scripts/generate_rsa_keys.py --key-id v1
```

把输出的 `RSA_KEY_ID` / `RSA_PRIVATE_KEY_PATH` / `RSA_PUBLIC_KEY_PATH` 写入 `services/erp/.env`。生产环境改为从密钥管理系统加载同一路径变量，不要把 PEM 打进镜像。

代码检查：

```bash
cd services/erp
uv run ruff check app tests
uv run pytest
```

Knowledge：

```bash
cd services/knowledge
uv sync
uv run alembic upgrade head
uv run python -m app
uv run pytest
```

说明见 `docs/knowledge.md`。

```bash
pnpm lint
pnpm build
pnpm test
```

## 验证清单

1. 打开 http://localhost:8015/login 可以注册并登录。
2. 登录后进入工作台，刷新页面应仍保持登录。
3. 未登录访问 `/erp/dashboard` 会跳到登录页，成功后回到原地址。
4. 直接打开 http://localhost:8016 或 http://localhost:8016/dashboard ，子应用可独立运行。
5. http://localhost:8011/docs 可打开 Swagger。
6. `/api/v1/health` 与 `/api/v1/auth/me` 可用。
7. 未登录打开主应用时，Network 里 `/auth/refresh` 可能 401，这表示没有 Refresh Cookie，属于预期，不应弹窗。
8. 公钥走 `GET /api/crypto/public-key`，不要求登录。
9. ERP 侧栏由 `apps/erp/src/router/routes.ts` 生成。
10. 登录成功后 Network 里不应立刻再出现 `/auth/refresh`；刷新页面才应恢复会话。
11. 登录后若没有企业，会进入 `/workspaces/create`；只有一家有效企业会自动进入；多家则优先恢复 `localStorage` 中该用户上次选择，失效则进入 `/workspaces`。
12. `POST /api/v1/tenants` 可创建企业；`GET /api/v1/tenants` 只返回自己加入的企业。创建企业不需要 `X-Tenant-ID`。
13. 业务接口用请求头 `X-Tenant-ID`，服务端会校验成员关系。切换企业不会调用登录或 Refresh。
14. 离开 `/erp` 再进入应恢复上次 ERP 页面；在 ERP 内切换企业后，保活探测输入应被清空，且 Network 里后续请求的 `X-Tenant-ID` 变为新企业。
15. 登录后创建企业，`GET /api/v1/roles`（带头 `X-Tenant-ID`）应看到 OWNER / ADMIN / OPERATOR / WAREHOUSE / VIEWER。
16. 未登录访问 `/api/v1/roles` 返回 401；普通成员 `POST /api/v1/roles` 返回 403。
17. ERP 侧栏「系统管理」可打开成员、角色、权限目录；OWNER 可添加已有账号或创建新账号。
18. 成员按钮按细粒度权限显示：无 `tenant:member:create` 看不到添加；无 `tenant:member:update` 不能改企业内名称。直接调接口仍 403。
19. 切换企业后成员/角色/权限目录变为新租户；`/system/members/:id` 会回到成员列表。
20. 代建账号成功后只展示一次临时密码；该账号登录后必须先改密（`40350`）。
21. 角色权限树保存后，当前用户菜单和按钮随 `my-permissions` 立即更新。DIRECTORY 节点不会被写成 Permission。
22. 使用中的自定义角色删除会提示人数（`ROLE_IN_USE`）；系统角色后端拒绝删除。
23. 登录并选择企业后，可进入「商品管理」创建类目、品牌、带多个 SKU 的商品；列表筛选和详情正常。
24. 有子类目或已被商品使用的类目不能删除（`CATEGORY_HAS_CHILDREN` / `CATEGORY_IN_USE`）；使用中品牌不能删除（`BRAND_IN_USE`）。
25. 切换企业后商品/类目/品牌变为新租户数据；无 `product:read` 看不到菜单，直接调接口仍 403。
26. 无 `product:create` 看不到新建商品；无 `product:update` 看不到编辑；OPERATOR 默认不能删除类目/品牌。
27. 新增商品可不填编码：服务端生成 `PD` + 10 位 id、`SKU` + 10 位 id；条码留空则等于最终 SKU 编码。用户自定义编码在租户内唯一。
29. 登录并选择企业后，可进入「仓库管理」创建仓库；第一个仓库自动成为默认仓库。第二个仓库可设为默认，列表只保留一个默认标记。
30. 未填仓库编码时服务端生成 `WH` + 10 位 id；自定义编码在租户内唯一。切换企业后仓库数据隔离。
31. 默认仓库不能直接停用或在还有其他仓库时删除；后端返回 `DEFAULT_WAREHOUSE_CANNOT_DISABLE` / `DEFAULT_WAREHOUSE_CANNOT_DELETE`。
32. 无 `warehouse:read` 看不到仓库菜单；无 create/update/disable/delete 时对应按钮隐藏，直接调接口仍 403。
33. 登录并选择企业后，可进入「库存管理」给仓库 + SKU 初始化库存，列表显示实际 / 预占 / 可用；可用 = 实际 - 预占。
34. 同一仓库 + SKU 不能重复初始化（`INVENTORY_ALREADY_EXISTS`）；减少超过可用库存失败（`INSUFFICIENT_AVAILABLE_INVENTORY`）。
35. 调整后可在「库存流水」看到 before/after；纠错靠新调整，不能改历史流水。
36. 无 `inventory:read` 看不到库存菜单；无 initialize/adjust 时对应按钮隐藏；无 `inventory:transaction:read` 看不到流水菜单。直接调接口仍 403。
37. 切换企业后库存与流水隔离；`/inventory/:id` 会回到库存列表。
38. 登录并选择企业后，可进入「供应商管理」创建供应商；未填编码时生成 `SUP` + 10 位 id。停用后不能新建采购单；已被采购单引用不能删除。
39. 可进入「采购单」选择供应商、仓库、多个 SKU 保存草稿；提交审核后核心字段锁定。管理员可审核通过（进入待收货）或驳回。
40. 创建或审核采购单后库存数量不变。无 `purchase:read` 看不到采购菜单；无 `purchase:audit` 看不到审核按钮。直接调接口仍 403。
41. 切换企业后采购单与供应商隔离；`/purchases/:id` 会回到采购列表。
42. 登录并选择企业后，可进入「客户管理」创建客户；未填编码时生成 `CUS` + 10 位 id。停用后不能新建销售订单；已被订单引用不能删除。
43. 可进入「销售订单」选择客户、履约仓库、多个 SKU 保存草稿。库存不足只提示，不阻止保存。提交后核心字段锁定，此时仍不预占库存。
44. 有 `order:audit` 的成员确认后，订单进入待出库：实际库存不变，预占增加，可用减少，流水为 `RESERVE` 且指向该订单。任一 SKU 不足则整单回滚，并列出 SKU、可用量和需求量。
45. 取消待出库会释放预占并写 `RELEASE`。再次取消返回 `ORDER_ALREADY_CANCELLED`。无 `order:read` 看不到订单菜单；无对应动作权限时按钮隐藏，直接调接口仍 403。
46. 切换企业后客户与销售订单隔离；`/orders/:id` 会回到销售订单列表。改客户地址不影响已保存订单的收货快照。
47. 可进入「物流商」创建承运商；未填编码时生成 `CAR` + 10 位 id。已被物流单引用不能删除，只能停用。停用后不能新建物流单。
48. 已确认出库的单据可创建物流草稿。草稿不改库存、不改变销售订单发货状态。确认发货前必须有运单号。
49. 确认发货后 `shipped_quantity` 增加，`Inventory.quantity` / `reserved_quantity` 不变。部分发货进入 `PARTIALLY_SHIPPED`，全部发货进入 `SHIPPED`。重复确认不再累计。
50. 已发货可追加轨迹；签收后自动写签收轨迹。全部物流签收后销售订单进入 `COMPLETED`。无对应权限时按钮隐藏，直接调接口仍 403。
51. 切换企业后物流商与物流单隔离；`/shipments/:id` 会回到物流单列表。
52. 已收货采购单详情可创建采购退货；可退数量基于已收货，不是采购计划数量。草稿不占用可退。
53. 提交后占用可退；审核可部分批准。确认退货出库后 `quantity` 减少、`reserved` 不变，流水 `PURCHASE_RETURN_OUTBOUND`。
54. `NO_REFUND` 全部出库后完成；`REFUND` 还需人工确认供应商退款。失败记录可重试新建。
55. 无 `purchase_return:read` 看不到采购退货菜单；无 outbound 时仓库员不能审核；无 `supplier_refund:confirm` 看不到确认退款。直接调接口仍 403。
56. 切换企业后采购退货 / 出库 / 供应商退款隔离；`/purchase-returns/:id` 会回到列表。
57. 工作台可选时间范围，看到销售额、净销售额、订单数、采购额、可用库存、售后率与待处理事项。取消单不计入销售额；成功退款减少净销售。
58. 数据中心可进入销售 / 采购 / 库存 / 售后分析，查看趋势、Top N、状态或仓库分布、低库存。
59. 无对应 `analytics:*:read` 看不到分析菜单；工作台仍对成员开放，KPI 按权限显示。直接调接口仍 403。
60. 切换企业后报表 Query Key 隔离，不闪现上一租户数字。导出 CSV 由后端按筛选生成。
61. 系统管理可进入事件中心、操作日志、任务中心。确认销售订单后事件中心出现 `SALES_ORDER_CONFIRMED`，操作日志出现对应 `CONFIRM`。
62. 销售分析可创建异步导出任务；任务中心看到排队 / 进度 / 成功后可下载。Worker：`uv run python -m app.tasks.worker`。
63. 无 `event:read` / `operation_log:read` / `task:read` 看不到对应菜单。操作日志不能修改或删除。切换企业后三类数据隔离。
64. 登录后进入「AI 知识库」工作台，可创建知识库、上传 PDF/DOCX/TXT/MD、查看解析预览与切片、重试失败任务。
65. 切换企业后工作台/文档/切片/任务不得闪现上一租户数据；详情路由退回工作台。无 `knowledge:read` 看不到入口；上传需 create，解析切片需 update，删除需 delete。
66. Knowledge API：http://127.0.0.1:8012/api/v1/health ，milestone 应为 Knowledge V3。`TASK_EXECUTOR=redis` 时另开 `uv run python -m app.tasks.worker`。Windows 请用 `uv run python -m app` 启动。
67. 智能搜索 / 知识问答 / 检索测试走同一检索引擎；切租户后旧 SSE 必须停止，`/chat/:id` 退回会话列表。模型配置页看不到 API Key。无检索结果时问答应说明证据不足。

多租户说明见 `docs/multi-tenancy.md`。RBAC 见 `docs/rbac.md`。商品见 `docs/products.md`。仓库见 `docs/warehouses.md`。库存见 `docs/inventory.md`。采购见 `docs/purchases.md`。销售订单见 `docs/orders.md`。履约见 `docs/fulfillment.md`。物流见 `docs/shipping.md`。盘点见 `docs/stocktake.md`。调拨见 `docs/stock-transfer.md`。售后见 `docs/after-sales.md`。退货见 `docs/returns.md`。采购退货见 `docs/purchase-returns.md`。报表见 `docs/analytics.md`。事件见 `docs/events.md`。操作日志见 `docs/operation-logs.md`。异步任务见 `docs/async-tasks.md`。知识库见 `docs/knowledge.md`。当前状态见 `docs/current-state.md`。V3 见 `docs/versions/v3.md`。V4 见 `docs/versions/v4.md`。V5 见 `docs/versions/v5.md`。V6 见 `docs/versions/v6.md`。V7 见 `docs/versions/v7.md`。V8 见 `docs/versions/v8.md`。V9 见 `docs/versions/v9.md`。V10 见 `docs/versions/v10.md`。V11 见 `docs/versions/v11.md`。V12 见 `docs/versions/v12.md`。V13 见 `docs/versions/v13.md`。V14 见 `docs/versions/v14.md`。V15 见 `docs/versions/v15.md`。路由配置说明见 `docs/routing.md`。认证流程见 `docs/auth.md`。文档导航见 `docs/README.md`。

## 浏览器进 debugger

业务错误会 `Promise.reject(ApiError)`。若一报错就停在 Sources 面板，检查 DevTools → Pause on exceptions，以及 Cursor/VS Code 调试器的 Caught Exceptions。代码里没有 `debugger`。

## 常见问题

**本机 8011 已被其他进程占用**

Neorvion 后端必须使用 8011。如果该端口已被占用，浏览器访问 `localhost:8011/docs` 会看到别的应用。请先结束占用进程，再启动本仓库后端：

```powershell
Get-NetTCPConnection -LocalPort 8011 | Select-Object OwningProcess,State
```

**子应用白屏**

- 页面曾经正常，切回标签或反复进入仍空白、只有整页刷新能恢复：见 `docs/micro-frontend-white-screen.md`。
- 确认 ERP 已启动在 8016。
- 确认 CORS 与 `server.origin` 仍为 `http://localhost:8016`。
- 确认入口调用了 `window.__WUJIE.mount()`。
- 无界依赖 iframe 沙箱。部分内嵌浏览器会拦截 iframe 的 `contentWindow`，请用系统 Chrome 打开 http://localhost:8015/erp。
- 子应用本身可用 http://localhost:8016 独立验证。

**MySQL / Redis 为 unavailable**

- 检查 `services/erp/.env` 账号是否与实际实例一致。FastAPI 只读取 `services/erp/.env`，仓库根目录 `.env` 给 Docker Compose 使用，二者可以不同。
- 业务库必须是 `neorvion_erp`，测试库是 `neorvion_erp_test`，不要复用其他项目数据库。
- 本机 3306/6379 可能已被其他服务占用，不要和 Docker 映射冲突。

**Docker 守护进程未启动**

- Compose 文件仍可使用，但需要先启动 Docker Desktop：
  `docker compose up -d mysql redis`
- Alembic 需要能连上 MySQL 后才能 `upgrade head`。M1 初始迁移为空，只打通命令链路。
