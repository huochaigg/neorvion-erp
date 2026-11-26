# 0004 生成卡住后发「取消」得到 40980，会话继续占死

- 状态：待修复
- 日期：2026-11-25
- 范围：前端停止/发送、`PersistentChatService.prepare`、会话 RUNNING 占位、断线收敛、`recover_stale`
- 关联：[0001](0001-sku-query-stuck-on-sales-order-review.md)、[0002](0002-pending-cancel-too-strict.md)、[0003](0003-intent-understanding-improvements.md)

## 复现

同一会话：

1. 发送：`分析下订单：SO2026000004`
2. UI 出现：`Agent 协作 · SINGLE_AGENT RUNNING`，内容区一直 loading，长时间无后续 token / done。
3. 用户试图结束：发送文本 `取消`（或先点停止再发别的话）。
4. 返回 SSE：

```text
event: error
data: {"code": 40980, "message": "该会话已有生成任务", "request_id": "..."}
```

5. 界面仍像卡在未完成轮次；同一会话后续提问继续被挡，直到陈旧任务被回收或刷新后碰巧恢复。

## 期望

- 生成中用户能**明确停止**当前轮：UI 停止按钮应立刻中止流，服务端把本轮助手消息收成 `CANCELLED`（或等价终态），释放会话锁。
- 停止成功后，用户立刻可以发新问题；不应再看到 40980。
- 聊天框里输入「取消」若发生在**生成进行中**，应被识别为「停止当前生成」，而不是开第二轮请求去撞锁；若发生在 **Skill/Intent Pending 补参**，才走补参取消语义（见 0002）。
- 服务端工具调用或模型调用长时间无进展时，应有可感知超时，并保证终态写入，避免会话永久 `RUNNING`。
- 40980 若仍发生，前端应给出可操作提示（「上一轮仍在运行，请先点停止」），并提供强制结束入口，而不是只显示 raw SSE error 后继续假 loading。

## 实际（对照源码）

### 1. 40980 是什么

`PersistentChatService.prepare`（`app/services/persistent_chat.py`）在建新轮前：

1. `recover_stale(stale_run_seconds)`（默认 **900 秒**）把过旧的 `RUNNING` 标成 `FAILED`（`error_code=50079`）。
2. 若会话里仍存在 `role=assistant` 且 `status=RUNNING` 的消息 → 抛 **`AppError("该会话已有生成任务", code=40980)`**。

即：**一会话同时只允许一轮生成**。第二轮请求（包括用户打的「取消」）在首轮未终态时一律 40980。

### 2. 前端「取消」≠ 停止生成

| 用户动作 | 前端行为 | 服务端效果 |
| --- | --- | --- |
| 点红色停止按钮 | `controller?.abort()` 中断当前 `fetch` SSE | 依赖 `request.is_disconnected`；图在检查点抛 49900，`events()` finally 把消息写成 `CANCELLED` |
| 生成中在输入框发「取消」 | `send()` 开头有 `if (running) return`，理论上发不出去 | — |
| 停止后（`running=false`）再发「取消」 | 新开一轮 `streamChat`，新的 `client_request_id` | 若首轮助手消息仍是 `RUNNING` → **40980** |
| Intent 补参卡片「取消本次补充」 | `send('取消')` | 意图/Skill Pending 取消口令，**不**负责杀掉正在跑的 Agent 图 |

本次现象与第三行高度吻合：首轮卡在 `SINGLE_AGENT RUNNING`，客户端已能再发消息，但库里的 RUNNING 占位还在，于是「取消」变成冲突请求。

### 3. 停止链路为什么会「点了停 / 能再发，锁却还在」

设计上断线收敛是有的：

- `CopilotWorkflow` / `MultiAgentWorkflow` 多处 `if await disconnected(): raise AppError(..., 49900)`。
- `PersistentChatService.events` 在未 `done` 时的 `finally` 会把消息和 AgentRun 标 `CANCELLED`（`error_code=49900`）。

仍会卡住的常见原因：

1. **断线检查不是抢占式的**：卡在一次长时间 `await` 工具 HTTP / 模型 stream、且中间不轮询 `disconnected` 时，abort 后服务端要等到该 await 返回才会收敛。调试器挂起、ERP 慢、模型无响应都会放大窗口。
2. **客户端 `running` 与服务端 `RUNNING` 不同步**：abort 后 `finally` 立刻 `setRunning(false)`，用户马上发下一条；服务端占位可能尚未写成终态 → 稳定复现 40980。
3. **没有「取消生成」API**：只能靠断开 SSE。没有 `POST .../cancel-run` 去主动 `finish_message`。
4. **陈旧回收太慢**：`stale_run_seconds=900`。15 分钟内同一会话都被 40980 挡死。
5. **40980 走 SSE `error` 事件**：`prepare` 失败时流里推 `event: error`；前端 `handleEvent` 只 `setError(message)`，**不会**清理服务端遗留 RUNNING，用户仍面对「有错 + 不能发」的状态。

### 4. 与「取消 Pending」的混淆

「取消」在项目里至少有三层含义：

1. 停止当前 SSE 生成（停止按钮 / abort）
2. 取消 Skill / Intent 参数收集（整句取消口令，见 0002）
3. 业务「取消订单」意图（`sales.order_cancel`，且当前不可执行）

用户在 **Agent RUNNING loading** 时输入「取消」，语义是 (1)，实现却容易变成「新聊天请求」撞上 (会话锁)，或在 Pending 场景变成 (2)。三层未在产品上分开，是体验陷阱。

## 临时绕过

1. 优先点输入框旁的**停止**按钮，等待几秒后再发新问题。
2. 若持续 40980：换一个新会话；或等待约 15 分钟让 `recover_stale` 把旧 `RUNNING` 收成失败。
3. 调试挂起时先从断点继续 / 停掉被阻塞的下游请求，再点停止。
4. 不要把「取消」当成生成中的停止口令；生成中应点停止。

## 相关代码

- `apps/copilot/src/pages/CopilotPage.tsx`：`send` 的 `running` 守卫；`onStop={() => controller?.abort()}`
- `apps/copilot/src/components/ChatComposer.tsx`：running 时只显示停止按钮
- `apps/copilot/src/api/chat.ts`：`fetch` + `AbortSignal` SSE
- `services/copilot/app/services/persistent_chat.py`：`prepare` → 40980；`events` finally → CANCELLED 49900
- `services/copilot/app/repositories/conversations.py`：`running_message`、`recover_stale`
- `services/copilot/app/core/config.py`：`stale_run_seconds: int = 900`
- `services/copilot/app/graph/workflow.py` / `multi_agent.py`：断线检查点
- `services/copilot/app/api/v1/chat.py`：SSE `error` 事件封装

## 后续可改方向（未实施）

**P0 体验**

- 生成中禁止把「取消」当新用户消息发出；停止按钮文案写清「停止生成」。
- abort 后客户端在收到终态（`done` / `error` 含取消）或短轮询会话详情确认无 `RUNNING` 之前，保持 `running` 或显示「正在停止…」，避免立刻发下一条撞 40980。
- 收到 40980 时提示「上一轮仍在运行」，并提供「强制停止本会话生成」操作。

**P0 服务端**

- 增加显式取消接口：按 `conversation_id`（+ 可选 `request_id`）把当前 `RUNNING` 助手消息与 AgentRun 标 `CANCELLED`，不依赖工具 await 自然返回。
- 工具执行 / 模型调用增加可中断超时，并在超时路径写入终态。
- 缩短可配置的 `stale_run_seconds`，或对「客户端已断开」加速回收。

**P1**

- 区分「停止生成」「取消补参」「取消订单」三套文案与 API，避免口令共用。
- 前端对长时间仅有 `agent_route` / `SINGLE_AGENT RUNNING`、无 token 的情况给出超时提示并自动建议停止。
- 评测/集成：abort 后立即再发消息必须成功，不得 40980。

## 验收标准（修复后）

1. 卡在 `SINGLE_AGENT RUNNING` 时点停止 → 数秒内助手消息变为 `CANCELLED`（或 FAILED 带明确错误），可立刻发新问题。
2. 停止后立刻发送任意新消息，不得再出现 40980。
3. 生成中输入「取消」不会开第二轮撞锁；或明确提示改点停止。
4. 人为让工具 hang 超过配置超时后，会话锁自动释放。
5. 40980 若仍返回，UI 有强制结束路径，而不是永久 loading。
