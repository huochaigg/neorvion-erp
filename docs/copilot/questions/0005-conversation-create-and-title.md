# 0005 Copilot 会话创建与标题管理优化

- 状态：方案整理（源码已核对；P0/P1 待实现）
- 日期：2026-11-25
- 范围：侧边栏新建对话、会话 CRUD、消息 `client_request_id` 幂等、标题字段与重命名 UI
- 性质：先确认真实行为，再对照目标交互列出缺口；**本次不改业务代码**
- 关联：[0004 生成卡住与 40980](0004-generation-stuck-cancel-40980.md)

阅读约定：

- **已实现**：当前代码已有，可直接用或只需小改接入。
- **部分实现**：能力有一半（例如可重命名，但无自动标题保护）。
- **待实现**：目标交互需要，源码中不存在。
- **待验证**：逻辑上可能出问题，尚无稳定自动化用例证明。

---

## 一、源码排查结论（六个问题）

### 1. 点击「新对话」是否立即创建数据库会话？

**是。立即创建。**

- 侧边栏按钮：`Sidebar.tsx` → `create.mutate()` → `createConversation()` → `POST /api/v1/conversations`，body `{ title: "新对话" }`。
- 后端：`ConversationService.create` → `ConversationRepository.create` → `flush` 插入 `copilot_conversations`。
- 成功后：`setSelectedId(row.id)`，并 `navigate('/chat')`。

另有第二入口：`CopilotPage.send` 在 `selected == null` 时也会 `create.mutateAsync()`，再发 SSE。这是「空白页首发」路径，同样立刻落库。

状态：**已实现（立即创建，非延迟创建）**

### 2. 为什么可以连续创建多个空白新对话？

**因为每次点击都发一次无幂等键的 create，且不要求有消息。**

- `POST /conversations` 无 `client_request_id` / Idempotency-Key。
- 创建不校验「是否已有无消息会话」。
- 侧边栏仅 `disabled={create.isPending}`，请求返回后可立刻再点。
- 连续点十次 → 十行 `title=新对话`、无消息的 `ACTIVE` 会话。

状态：**已确认行为；相对目标交互为待优化（P0）**

### 3. 是否存在无消息的历史会话记录？

**会。**

- 列表：`GET /conversations` → `repo.list`，过滤 `status=ACTIVE` 且未软删，**不**按是否有消息过滤。
- 空会话会出现在历史列表；标题均为「新对话」。
- 删除是软删：`status=DELETED` + `deleted_at`，列表不再显示。

状态：**已确认存在；相对目标交互为待优化（P0）**

### 4. 当前标题从哪里生成？是否始终用固定默认名？

**前端写死默认「新对话」，无 LLM 标题。**

| 位置 | 行为 |
| --- | --- |
| `apps/copilot/src/api/conversations.ts` | `createConversation(title = '新对话')` |
| `ConversationCreate` | Field default `"新对话"` |
| DB `copilot_conversations.title` | `server_default="New conversation"`（与前端中文默认并存） |
| 首条消息后 | **不会**改标题 |
| 全仓库检索 | 无 `title_source`、无 `TitleGenerationService`、无自动标题任务 |

状态：**部分实现（仅有静态默认标题）**；自动标题 **待实现（P1）**

### 5. 是否支持用户手动修改标题？

**支持（前后端都有）。**

- API：`PATCH /api/v1/conversations/{id}`，`ConversationRename`，`ConversationService.rename`（按 tenant/user 取会话 + 行锁）。
- UI：侧边栏会话行铅笔 → Modal「重命名会话」→ `renameConversation`。
- **没有** `title_source=MANUAL` 标记；因目前无自动生成，暂无「自动覆盖手动」冲突。一旦上自动标题，必须补保护字段。

状态：**已实现（手动重命名）**；覆盖保护 **待实现（P1）**

### 6. 会话创建、消息发送与 SSE 的幂等关系？

| 环节 | 幂等手段 | 结论 |
| --- | --- | --- |
| 创建会话 | 无 | 每次 POST 新行 |
| 发送消息 | `client_request_id`（会话内 + role 唯一） | 同 ID 重放：RUNNING→40981；COMPLETED→回放答案；其他终态→40982 |
| 同会话并发生成 | 只允许一条 assistant `RUNNING` | 否则 40980（见 0004） |
| 首条消息且无 selected | 先 create 再 SSE | create 本身无幂等；SSE 阶段才有 message 幂等 |
| 离开页面 | `CopilotPage` unmount `controller?.abort()` | 停当前流；服务端依赖断线收敛；无「后台继续」策略文档化产品行为 |

`begin_turn` 会更新会话 `updated_at`，列表按 `updated_at desc, id desc` 排序——**有消息后的活动排序已实现**；空会话之间只按创建时间挤在一起。

状态：**消息幂等已实现；会话创建幂等待实现；离开页策略部分实现 / 待产品定稿**

---

## 二、目标交互 vs 当前差距

### 1. 新对话

| 目标 | 当前 | 差距 |
| --- | --- | --- |
| 侧边栏固定一个「+ 新对话」 | 有「新建对话」按钮（展开/折叠各一） | 基本符合；文案可统一为「新对话」 |
| 点击切到空白页 | 立即 create + 选中 | **不应**先落库 |
| 延迟创建：未发送不建库 | 立即建库 | P0 待实现 |
| 连续点击不产生多条空会话 | 会 | P0 |
| 首发幂等创建正式会话 | create 无幂等键 | P0 |
| 创建成功后进历史并按活动排序 | 进历史；排序按 updated_at | 空会话污染列表；有消息后排序可用 |
| 重试不重复会话 | 不保证 | P0 |
| 未完成流离开页：取消或继续 | unmount abort；无显式「继续」 | 待产品定稿 + 0004 |

### 2. 会话标题

| 目标 | 当前 | 差距 |
| --- | --- | --- |
| 首发后临时标题 | 一直是「新对话」 | P1 |
| 低成本 LLM 异步短标题 | 无 | P1 |
| 不阻塞聊天 | — | 设计时需遵守 |
| 失败保留临时标题 | — | P1 |
| 默认只自动生成一次 | — | P1 |
| 手动重命名 | 有 | 已实现 |
| 手动后禁止自动覆盖 | 无字段 | P1 |
| 可选重新生成 | 无 | P2 |

---

## 三、推荐技术设计（实施时，非本次编码）

### 会话状态（建议）

```text
NEW（仅前端草稿，无 DB id）
  → CREATING（首发携带 idempotency_key 创建中）
  → ACTIVE（DB 已有会话）
创建失败 → ERROR（可用同一幂等键重试）
```

当前 DB 只有 `ACTIVE` / `DELETED`，不必把 NEW 写入库；NEW 留在前端即可。

### 标题状态（建议）

```text
DEFAULT → GENERATING → AUTO
用户改名 → MANUAL（禁止普通自动任务覆盖）
可选：用户触发 REGENERATE，仍不得覆盖 MANUAL，除非显式确认
```

建议字段（评估后加迁移）：

- `title_source`: `DEFAULT | AUTO | MANUAL`
- `title_generated_at` / 可选 `title_version` 做条件更新
- 创建 API 增加可选 `idempotency_key`（或复用首条 `client_request_id` 派生）

### 后端复用

优先复用：

- `ConversationService` / `PersistentChatService`
- `client_request_id` 消息幂等
- 现有 `PATCH` 重命名与软删
- 租户 + user 归属校验
- 已有异步任务 / 配额基础设施（若做标题 LLM）

评估新增：

- `TitleGenerationService`（异步、失败降级）
- 创建幂等（空会话复用或 idempotency 表）
- `title_source` 与条件更新（`WHERE title_source != 'MANUAL'`）

安全：标题任务不得越权改他人会话；自动标题 prompt 按不可信用户文本边界处理。

### 前端

- 「新对话」只 `setSelectedId(null)` + 清本地 draft / Pending / intent / agent 状态，**不**调 create。
- 区分 `draft` 与已持久化 id；首发锁定重复提交。
- 创建成功后同步 selectedId、列表、可选 URL。
- 切换草稿时不得复用旧会话的 Skill Pending、Intent Pending、AbortController、SSE 状态（与 0001/0004 相关）。

---

## 四、问题条目（统一结构）

### C-01 新对话立即落库导致空会话堆积

- 优先级：P0
- 状态：待实现（相对目标）；当前行为已确认
- 当前实现：Sidebar / CopilotPage → `POST /conversations`
- 风险：历史列表被「新对话」刷屏；误点产生垃圾数据
- 方案：延迟创建；点击仅进前端 NEW；可选「复用用户名下最新空会话」作过渡
- 验收：连点十次新对话，库中不新增十条空记录

### C-02 会话创建无幂等键

- 优先级：P0
- 状态：待实现
- 当前实现：create 无 client 幂等
- 风险：首发网络重试 / 双击 → 多个空会话或重复会话
- 方案：首发用同一 idempotency_key 创建；冲突返回已有 id
- 验收：同一幂等键重复提交只产生一个会话；消息侧仍用 `client_request_id`

### C-03 跨会话 / 草稿切换状态隔离

- 优先级：P0
- 状态：部分实现 / 待验证
- 当前实现：选中会话会换 detail query；unmount abort；Pending 与 selected 有部分绑定
- 风险：快速「新对话」时旧 SSE、Intent/Skill Pending、draft 串台（见 0001/0004）
- 方案：切换 selected/draft 时显式 reset running 状态机；禁止跨 conversation 复用 runtime
- 验收：新对话不继承旧 Pending / Skill / 意图上下文；旧流 abort 且不写到新草稿

### C-04 自动标题生成

- 优先级：P1
- 状态：待实现
- 当前实现：固定「新对话」
- 方案：首条有效用户消息后异步生成；临时标题可用消息截断；失败保留临时标题；只自动一次
- 验收：自动标题失败不影响聊天；默认不反复改名

### C-05 手动标题保护

- 优先级：P1
- 状态：待实现（手动改名已有）
- 当前实现：`rename` 直接改 `title`
- 方案：`title_source=MANUAL`；自动任务条件更新跳过 MANUAL
- 验收：手动改名后，迟到的自动标题任务不能覆盖

### C-06 重新生成标题 / 列表体验

- 优先级：P2
- 状态：待实现
- 方案：菜单「重新生成」仅对 AUTO/DEFAULT；归档；标题质量评测另册
- 验收：MANUAL 需确认才可重生；列表分页与搜索保持可用

### C-07 离开未完成流的产品策略

- 优先级：P1（与 0004 合并推进）
- 状态：部分实现
- 当前实现：unmount abort；无「后台继续」
- 方案：文档化并实现其一——离开即取消（推荐）或显式「后台运行」+ 可取消
- 验收：与 0004 停止/40980 验收一并过

---

## 五、测试清单（修复后补齐）

1. 连续点击新对话十次，不产生十条空记录。
2. 第一条消息重复提交，不重复创建会话。
3. SSE 中断和网络重试，不生成重复会话。
4. 自动标题失败，不影响聊天。
5. 用户手动改名后，自动生成任务不能覆盖。
6. 多租户、不同用户不能修改彼此的会话标题（现有 rename 已按 owner 过滤，需回归）。
7. 历史会话按最近活动排序、分页与重新加载。
8. 新对话不会继承旧对话 Pending、Skill 和意图识别上下文。

---

## 六、优先级

| 级 | 项 |
| --- | --- |
| P0 | C-01 空会话、C-02 创建幂等、C-03 跨会话隔离 |
| P1 | C-04 自动标题、C-05 手动保护、C-07 离开流策略 |
| P2 | C-06 重生标题、归档、质量评测、列表体验 |

## 七、实施要求（给后续开发）

1. 以本文源码结论为准，不要假定已有延迟创建或 LLM 标题。
2. 优先复用 conversations CRUD、消息幂等、rename；避免第二套会话表。
3. 先做 P0，再接通异步标题。
4. 改代码前补测试；本次文档阶段不改业务代码、不做 git 写入。

## 八、相关代码索引

- `apps/copilot/src/components/Sidebar.tsx`：新建 / 列表 / 重命名 / 删除
- `apps/copilot/src/pages/CopilotPage.tsx`：selected 为空时 create + SSE
- `apps/copilot/src/api/conversations.ts`：默认 title「新对话」
- `services/copilot/app/api/v1/conversations.py`：CRUD + messages SSE
- `services/copilot/app/services/conversations.py`：create / rename / delete
- `services/copilot/app/services/persistent_chat.py`：prepare 幂等与 RUNNING 锁
- `services/copilot/app/models/conversation.py`：title 无 source 字段；状态仅 ACTIVE/DELETED
- `services/copilot/app/repositories/conversations.py`：`order_by(updated_at.desc())`
