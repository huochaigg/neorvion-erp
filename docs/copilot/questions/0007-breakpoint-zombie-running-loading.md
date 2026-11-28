# 0007 断点挂起过久后助手消息永久 RUNNING / loading

- 状态：已修复（见 [Chat Run 生命周期](../architecture/chat-run-lifecycle.md)）
- 日期：2026-11-26
- 范围：debugpy 挂起、`PersistentChatService.prepare` / `events`、SSE 取消、`recover_stale`、前端 `RUNNING` loading
- 关联：[0004](0004-generation-stuck-cancel-40980.md)（同一把会话锁；0004 是再发消息撞 40980，本文是首轮占位从未写成终态）

## 复现

本地 Copilot 用 debugpy 挂在 `8013`。发送一条消息后停在断点，长时间不继续。关掉断点（继续执行或结束调试）后：

- UI 该轮助手一直是三个点 loading
- 拉会话消息列表，最后一条助手类似：

```json
{
  "id": 150,
  "role": "assistant",
  "content": "",
  "status": "RUNNING",
  "request_id": "5f9f208f4e7c451cb07f93db2158a094",
  "created_at": "2026-11-26T12:17:26.824916+08:00",
  "updated_at": "2026-11-26T12:17:26.824916+08:00",
  "tool_runs": [],
  "evidences": [],
  "agent_runs": [],
  "skill_runs": [],
  "intent_status": null
}
```

特征：`content` 空、`status=RUNNING`、`created_at` 与 `updated_at` 相同、没有 Agent/Tool/Skill 记录。刷新页面仍 loading。

## 期望

- 客户端断开、请求被取消、调试进程被停掉后，已落库的助手占位必须写成 `CANCELLED` 或 `FAILED`，不能长期 `RUNNING`。
- GET 会话详情不应把僵尸 `RUNNING` 渲染成「仍在生成」。
- 陈旧回收不应只在「下一次发消息」时才跑，也不应默认要等 900 秒。
- 调试挂起导致下游超时后，恢复执行仍应收敛终态，而不是既不吐 token 也不改库。

## 实际（对照源码）

### 1. 为什么库里会先有一条空的 RUNNING 助手

`PersistentChatService.prepare` 在模型开跑之前就会 `begin_turn` 并 **commit**：

- 用户消息：`COMPLETED`
- 助手消息：`content=""`，`status=RUNNING`

见 `app/services/persistent_chat.py` `prepare` / `app/repositories/conversations.py` `begin_turn`。

这是有意设计：短事务占住「一会话一轮生成」锁。因此断点只要停在 **commit 之后、终态写入之前**，刷新 GET 就会看到这条空 RUNNING。

本条快照 **没有 `agent_runs`**，说明多半还没进 `events()`（那里才会 `begin_agent_run`）。典型卡点：`chat.py` 里 `prepare` 之后的 `_prepare_with_intent`（意图 / Skill 选择），或刚进入 Graph、第一条 `agent_start` 还没落库。

前端 `ChatMessage`：`status === 'RUNNING' && !content` 就画三个点。`composeVisibleMessages` 也会把最后一条 RUNNING 助手换成 live streaming 气泡。GET 回来仍是 RUNNING 时，即使 `send()` 已经 `finally setRunning(false)`，loading 也不会消失。

### 2. 断点挂久了之后，请求往往已经死了，占位还活着

debugpy 断点会卡住 **整个 asyncio 事件循环**。这段时间里：

1. SSE 不再往浏览器推数据，浏览器 / 代理可能关掉 fetch。
2. 模型、ERP 的 httpx 超时在墙钟时间上继续走，但协程冻住，超时回调也跑不了。
3. 关掉断点后常见两种结局：
   - **继续（F5）**：生成器被客户端取消，抛出 `asyncio.CancelledError`（Python 3.11+ 继承 `BaseException`，**不是** `Exception`）。
   - **结束调试（红点停止）**：进程直接没了，任何 `finally` 都不会写库。

`event_stream`（`app/api/v1/chat.py`）只对 `AppError` / `Exception` 调用 `fail_before_run`。`CancelledError` 和进程被杀都不会走这两条。`finally` 里对 **持久化会话** 也不会 `finish_message`（只处理无 `conversation_id` 的 Skill 失败和配额）。

`PersistentChatService.events` 自己的 `finally` 能把消息写成 `CANCELLED`（49900），但前提是 **已经进入 `events()`**。若断在 `prepare` 与 `events()` 之间（与本条空 `agent_runs` 一致），这条路径根本不会跑。

于是：客户端 loading 结束或刷新后，库里的助手仍是 RUNNING。

### 3. 陈旧回收帮不上当前这一屏

`recover_stale(stale_run_seconds)` 默认 **900 秒**，且 **只在下一次 `prepare`（再发一条消息）时** 执行。GET 会话详情不回收。

因此：

- 刷新页面：仍 RUNNING，仍三个点。
- 立刻再发：未满 15 分钟 → **40980**「该会话已有生成任务」（见 0004）。
- 等 15 分钟后再发：旧消息被标 `FAILED` / `error_code=50079`，新轮才能开始。回收不会补全文，只改状态。

### 4. 与 0004 的差别

| | 0004 | 0007（本条） |
| --- | --- | --- |
| 用户动作 | 卡住后点停止 / 再发「取消」 | 断点挂很久再关掉 |
| 立刻看到的 | SSE `40980` | 本轮一直 loading |
| 库状态 | 已有 RUNNING，第二轮被拒 | 同一条 RUNNING 从未终态 |
| 根因侧重 | 客户端 `running` 与服务端锁不同步；无取消 API | 占位 commit 后取消/杀进程不收敛；GET 不扫僵尸 |

同一把锁：`running_message()` 只要看到 assistant RUNNING 就 40980。

## 当前怎么把这一轮救出来（不改代码）

任选其一：

1. **新开对话**（最快）。旧会话 15 分钟内无法正常续聊。
2. 在该会话再发一条任意消息：若已超过约 15 分钟，`recover_stale` 会把 id=150 收成 FAILED，新轮可以开始；未满 15 分钟会 40980。
3. 本地库把该助手打成终态后再刷新页面，例如将 `copilot_messages.id=150` 的 `status` 改为 `CANCELLED` 或 `FAILED`，并写 `completed_at`。不要改用户那条。

调试时：不要在 `prepare` commit 之后长时间停住；需要停就尽快继续或停掉 Copilot 进程前先点 UI 停止。单步工具调用请把 `TOOL_TOTAL_TIMEOUT_SECONDS` 临时调大（与此前 50472 相同）。

## 相关代码

- `services/copilot/app/services/persistent_chat.py`：`prepare` 先 commit RUNNING；`events` finally 仅覆盖已进入 Graph 的轮次；`fail_before_run`
- `services/copilot/app/repositories/conversations.py`：`begin_turn`、`finish_message`、`running_message`、`recover_stale`
- `services/copilot/app/api/v1/chat.py`：`event_stream` 的 `except AppError/Exception` 不含 `CancelledError`；`finally` 不收敛持久化 RUNNING
- `services/copilot/app/core/config.py`：`stale_run_seconds = 900`
- `apps/copilot/src/components/ChatMessage.tsx`：空内容 RUNNING → loading 点
- `apps/copilot/src/pages/CopilotPage.tsx`：`send` finally 只 `invalidateQueries`，不把 RUNNING 本地改成失败

## 后续可改方向（未实施）

**P0**

- `event_stream` 对 `BaseException` / `CancelledError` / 生成器 `finally`：只要 `persistent_turn` 已创建且未 `completed`，就 `fail_before_run` 或标 `CANCELLED`。
- GET 会话（或启动时）对超时 RUNNING 做与 `recover_stale` 相同的收敛，避免刷新后假 loading。
- 显式「停止生成」API（与 0004 相同），不依赖断点解开后事件循环自己醒过来。

**P1**

- 缩短开发环境 `stale_run_seconds`，或对「无 AgentRun、无 token」的占位用更短 TTL（例如 60s）。
- 前端发现详情里 RUNNING 且 `updated_at` 过旧、无 draft：展示「生成已中断」和「标记失败并重试」，不要一直三个点。
- 进程退出钩子（尽量）把本进程未完成的 RUNNING 标失败；杀进程仍要靠 TTL。

## 验收标准（修复后）

1. `prepare` 之后、`events` 之前取消请求或停调试：该助手不得保持 RUNNING；刷新后无 loading。
2. 断点挂起超过客户端断开时间再 Continue：消息为 CANCELLED/FAILED，可立即发下一句，无 40980。
3. 仅刷新会话详情也会把超过 TTL 的 RUNNING 收掉。
4. 本条复现快照（空 content、无 agent_runs）在修复后不应再稳定出现。
