# Copilot 多轮聊天卡死 / CPU 升高排查报告

日期：2026-11-25  
范围：`apps/copilot` 聊天页、SSE 客户端、消息渲染；对照 `services/copilot` 流式协议  
结论级别：用户提供的真实 SSE 已证实 **Markdown 解析死循环** 会在流式输出标题时立刻卡死；此前的全量重渲染/平滑滚动是累积变慢因素。死循环已修并有回归测试。

---

## 1. 问题根因

### 1.1 已证实（源码 + Node 基准）

多轮后卡死/CPU 升高不是单一死循环，而是 **每个 SSE token 触发整页工作，且成本随历史消息线性累积**。

| 编号 | 根因 | 级别 | 依据 |
| --- | --- | --- | --- |
| R1 | 每个 `message` delta 立刻 `setDraft`，`CopilotPage` 重渲染整份 `visible` 列表 | 已证实 | `CopilotPage` 原 `handleEvent` 对 `message` 直接 `setDraft`；`composeVisibleMessages` 每次返回新数组 |
| R2 | `ChatMessage` / `SafeMarkdown` 未 memo，历史 Markdown 每个 token 全量重解析、重生成 React 节点 | 已证实 | 组件无 `memo`；`parseMarkdownBlocks` 每个 render 都跑。Node 基准：16 条历史 × 60 token，全量解析 13.62ms，仅解析直播消息 0.99ms，**约 13.8 倍** |
| R3 | 每个 draft/tools 变化调用 `scrollIntoView({ behavior: 'smooth' })` | 已证实 | 原 `CopilotPage` `useEffect` 依赖 `draft`。平滑滚动会被下一 token 打断，并在 `onScroll` 里读 `scrollHeight`/`scrollTop`，形成布局抖动。历史越长，滚动距离和布局成本越大 |
| R4 | 会话切换后旧 SSE 仍可写当前页的 `draft/tools` | 已证实 | `handleEvent` 原先只比 `runRef`，不比 `selectedId`。`CopilotPage` 不随会话卸载，旧流会让新会话列表跟着重渲染 |
| R5 | 停止/卸载时 SSE `ReadableStream` reader 未主动 `cancel` | 已证实 | `consumeSse` 原实现没有 `AbortSignal`，只靠 `fetch` 中断；Wujie 代理下这不一定立刻停止消费 |
| **R6** | **流式 Markdown 标题 `# ` 使 `parseMarkdownBlocks` 死循环** | **已复现** | 用户刷新后重发，SSE 在 `delta:"#"` 再 `delta:" "` 后页面崩溃。标题正则原为 `/^(#{1,3})\s+(.+)$/`，`# ` 匹配失败；段落分支又用 `/^#{1,3}\s+/` 把它当新块并 `break`，`index` 不前进。`SafeMarkdown` 永不返回，主线程 100%。 |

后端按模型 delta 推 token（`services/copilot/app/graph/workflow.py` 约 140–147 行），前端没有自动重连。因此：

- **不是** SSE 重连风暴。
- **不是** `useEffect` 状态互相触发的无限 React 渲染。
- **瞬时卡死** 的主因是 R6：模型一开始输出 Markdown 标题（`# `）就死循环。多轮后更容易出现，因为助手更常以标题开篇；刷新再发同样会中招。
- **累积变慢** 来自 R1–R3：高频 token × 全历史 Markdown/DOM + 平滑滚动。

### 1.2 推测（源码风险，无浏览器 Profiler 数据）

| 编号 | 风险 | 级别 |
| --- | --- | --- |
| S1 | 直播气泡里的 antd `Collapse`（`AgentExecutionPanel`）在 token 期间仍会随直播消息重渲染，可能贡献 Long Task | 推测 |
| S2 | `.copilot-fade` 在 key 变化时重挂载会重放动画；key 含 `index` 时插入消息可能带动后续项 | 推测，已改为稳定 key 降低风险 |
| S3 | Wujie `alive=true` 时若宿主未走 `__WUJIE_UNMOUNT`，后台仍可能跑动画/未完成流 | 推测。当前子应用 `main.tsx` 在 unmount 时会卸 React 根并 abort |
| S4 | `skill_resource_loaded` 把同一资源写进所有 SkillRun；`evidence` 无去重。事件异常多时数组变长 | 静态风险，未见无限循环 |

### 1.3 已排除

- 前端没有 `EventSource` 自动重连，`streamChat` 失败只进 `error`，不会指数重试。
- 聊天路径没有 `setInterval`；`WorkbenchLayout` 只有 `matchMedia` 监听并在 effect 清理。
- React Query 聊天详情 `refetchOnWindowFocus: false`，流式过程中不会因为切窗反复拉历史。
- 未发现 SSE 事件在客户端被同一监听器重复注册；每次 `send()` 一个 `fetch` + 一个 `consumeSse`。

---

## 2. 调用链（以源码为准）

```
用户输入 / 快捷问题
  → CopilotPage.send()
      → 无会话时 createConversation()（POST /api/v1/conversations）
      → streamChat()  POST /api/v1/conversations/{id}/messages
           Accept: text/event-stream, AbortSignal
  → FastAPI send_conversation_message()
      → chat.chat_stream() → event_stream() yield SSE
      → Workflow.adapter.stream() 每个 delta.text 推 event: message
      → tool/agent/skill/intent/evidence 各自 event
  → consumeSse() 解析 event/data
  → createStreamFrameQueue.push()   （修复后：token 按帧合并）
  → CopilotPage.handleEvent()
      → setDraft / setTools / setAgentRun / setSkillRuns / setIntentStatus / setEvidences
  → composeVisibleMessages()
  → ChatMessage 列表 + SafeMarkdown + Tool/Agent/Skill/Evidence
  → 滚动容器 scrollTop = scrollHeight（贴底时，按 rAF）
  → 流结束 finally：flush 队列、invalidate 会话详情
```

### 入口与模块

| 角色 | 路径 |
| --- | --- |
| 页面入口 | `apps/copilot/src/pages/CopilotPage.tsx` → `send` / `handleEvent` |
| 路由 | `apps/copilot/src/App.tsx` `/chat` |
| SSE API | `apps/copilot/src/api/chat.ts` `streamChat` |
| SSE 解析 | `apps/copilot/src/lib/sse.ts` `consumeSse` |
| 帧合并 | `apps/copilot/src/lib/streamUi.ts` `createStreamFrameQueue` |
| 消息拼装 | `apps/copilot/src/lib/chatMessages.ts` `composeVisibleMessages` |
| 列表项 | `apps/copilot/src/components/ChatMessage.tsx` |
| Markdown | `apps/copilot/src/components/SafeMarkdown.tsx` |
| 进度卡片 | `ToolRunCard` / `AgentExecutionPanel` / `SkillRunCard` / `IntentStatusCard` / `EvidenceCard` |
| 输入框 | `ChatComposer` `onSend` / `onStop` |
| 会话列表 | `Sidebar.openConversation` → `setSelectedId` |
| 全局 abort | `apps/copilot/src/store.ts` `controller`；切租户 `switchTenant` / `reset` |
| Wujie 宿主 | `apps/shell/src/micro/CopilotMicroApp.tsx` `alive={true}` |
| Wujie 子应用 | `apps/copilot/src/main.tsx` `__WUJIE_MOUNT` / `__WUJIE_UNMOUNT` |
| 后端 SSE | `services/copilot/app/api/v1/conversations.py` 59–80；`chat.py` `event_stream` |

### 定时器 / 连接 / 监听

| 资源 | 修复前 | 修复后 |
| --- | --- | --- |
| SSE | 每次 `send` 一个 `fetch`；`AbortController` 存在但 reader 不 `cancel` | `consumeSse` 监听 abort 并 `reader.cancel()` |
| rAF | 无（平滑滚动由浏览器自己做） | token 合并队列 + 滚动各一个 rAF，卸载时取消 |
| `scrollIntoView smooth` | 每个 token | 已删除 |
| `matchMedia` | `WorkbenchLayout` 有清理 | 未改 |
| Wujie bus | `WujieRouteBridge` / `TenantBridge` `$on` 有 `$off` | 未改 |
| 自动重连 | 无 | 无 |
| 组件卸载 | abort controller | 同时 `queue.close()`、cancel scroll rAF、abort |

---

## 3. 触发过程

1. 第 1 轮：历史为空，每个 token 只解析直播 Markdown，再平滑滚到底。通常可接受。
2. 第 N 轮：历史里已有多段带表格/代码块的助手消息。每个 token 仍：
   - 复制整个 `messages` 数组；
   - 重新执行全部 `ChatMessage`；
   - 对每条历史再跑 `parseMarkdownBlocks` + `renderInline`；
   - 再启动一次 `behavior: 'smooth'` 滚动。
3. 模型输出越快、表格越大、自动贴底越勤，主线程越容易出现连续 Long Task，表现为输入无响应、风扇/CPU 升高。
4. 若此时再切历史会话，旧流的 `setDraft` 仍打在同一 `CopilotPage` 上，新会话的历史列表也会跟着刷。
5. 中途点停止：若 reader 未 cancel，token 仍可能进 UI（修复后先 `queue.close()` 再 abort）。

---

## 4. 优化方案与原理

1. **渲染边界**：`ChatMessage`、`SafeMarkdown` 使用 `React.memo`。`composeVisibleMessages` 保持历史消息的对象引用，token 更新只换掉 `id === -1` 的直播消息，历史项 props 不变则跳过 Markdown。
2. **按帧合并 token**：`createStreamFrameQueue` 把同一帧内的 `message` delta 拼成一次 `setDraft`；`tool_*` / `agent_*` / `skill_*` 等控制事件先 `flush` 再同步处理，保证顺序。流正常结束 `flush`，取消则 `close` 丢弃未刷帧，最后一批 token 不丢。
3. **滚动**：容器 `scrollTop = scrollHeight`，rAF 最多每帧一次，去掉 smooth。用户上翻超过 80px 仍用 `autoScroll` ref 停止跟随。
4. **SSE 生命周期**：`consumeSse(response, onEvent, signal)` abort 时 cancel reader，不再回调后续事件。停止、切会话、卸载都先关队列再 abort。
5. **会话隔离**：`shouldApplyStreamEvent` 同时校验 `runId` 和 `selectedId`。切走正在生成的会话会 abort，避免旧事件改新会话。
6. **稳定 key**：`visibleMessageKey`，正数 id 用 `msg-{id}`，避免 index 造成错挂载。

未引入虚拟列表或新状态库：当前瓶颈是“历史被每个 token 重做”，memo + 帧合并即可对症；虚拟列表要等真实 DOM 节点数成为瓶颈后再考虑。

---

## 5. 修改文件清单

| 文件 | 变更 |
| --- | --- |
| `apps/copilot/src/pages/CopilotPage.tsx` | 帧队列、会话 abort、rAF 滚动、事件隔离、稳定 key、停止时关队列 |
| `apps/copilot/src/lib/streamUi.ts` | 新增队列与 `shouldApplyStreamEvent` |
| `apps/copilot/src/lib/streamUi.test.ts` | 隔离 / 合帧 / 取消丢 token |
| `apps/copilot/src/lib/sse.ts` | abort 取消 reader |
| `apps/copilot/src/lib/sse.test.ts` | abort 回归 |
| `apps/copilot/src/api/chat.ts` | 把 `signal` 传给 `consumeSse` |
| `apps/copilot/src/lib/chatMessages.ts` | `visibleMessageKey` |
| `apps/copilot/src/lib/chatMessages.test.ts` | 历史引用保持 |
| `apps/copilot/src/components/ChatMessage.tsx` | `memo` |
| `apps/copilot/src/components/SafeMarkdown.tsx` | `memo`，导出 `parseMarkdownBlocks` |
| `apps/copilot/src/components/SafeMarkdown.test.tsx` | XSS + 解析成本对照 |
| `docs/copilot/questions/README.md` | 索引 |

未改：权限、审批、SSE 事件名/字段、后端协议。

关键修复位置（修复后行号）：

- 滚动：`CopilotPage.tsx` 148–156、154（`scrollTop`）
- 事件守卫：158–168
- token 合帧：339–343、382–384、395–401
- 停止：485–488
- `setDraft`：287（仍按事件追加，但事件已按帧合并）
- `consumeSse`：`apps/copilot/src/lib/sse.ts` 9–74
- `ChatMessage` memo：`ChatMessage.tsx` 10
- `SafeMarkdown` memo：`SafeMarkdown.tsx` 128–129

---

## 6. 修复前后性能对比

### 6.1 已测量（Node / Vitest，本机 2026-11-25）

场景：16 条含 24 行表 + 代码块的历史 Markdown，60 次 token 追加。

| 指标 | 修复前模型（每 token 解析全部历史） | 修复后模型（历史解析一次 + 只解析直播） | 来源 |
| --- | --- | --- | --- |
| `parseMarkdownBlocks` 耗时 | **13.62 ms** | **0.99 ms** | `SafeMarkdown.test.tsx`，`ratio=13.80` |
| 同帧 token 回调次数 | 每个 delta 一次 `setDraft` | 合并为 1 次 `onEvent` | `streamUi.test.ts` |
| 历史消息对象引用 | 每次 `composeVisibleMessages` 保留原引用（原本已如此） | 不变，现被 `memo` 真正用上 | `chatMessages.test.ts` |

复现命令：

```bash
cd apps/copilot
pnpm exec vitest run src/components/SafeMarkdown.test.tsx --disable-console-intercept
```

### 6.2 未测量（无登录态，无法进真实 Copilot）

尝试打开 `http://localhost:8015/`，停留在登录页「欢迎回到 Neorvion」，没有可用测试账号，因此下列指标 **未验证**：

- Chrome Performance 主线程 CPU / Long Task
- React Profiler 组件渲染次数与单次耗时
- JS Heap
- 活跃 SSE 连接数（实机）
- 10～20 轮真实对话的体感流畅度
- DOM 节点数

不要把 13.8 倍解析成本直接当成“页面快了 13.8 倍”。它只证明历史全量重解析是真实、可累积的 CPU 来源。

---

## 7. 回归测试

`apps/copilot`：`pnpm test` → **18 files / 37 tests passed**。

覆盖：

| 要求 | 测试 | 结果 |
| --- | --- | --- |
| 同一 SSE 事件不重复消费；token 合帧 | `streamUi.test.ts` | 通过 |
| 旧 run / 旧会话事件不应用 | `shouldApplyStreamEvent` | 通过 |
| 取消后不再更新 UI | `createStreamFrameQueue.close` | 通过 |
| abort 取消 reader | `sse.test.ts` | 通过 |
| 历史引用稳定，长消息不必随 token 换对象 | `chatMessages.test.ts` | 通过 |
| Markdown 不注入 HTML | `SafeMarkdown.test.tsx` | 通过 |
| 历史全量解析 vs 隔离直播 | 同上，full > isolated × 4 | 通过 |
| 原有会话拼装 / SSE 跨 chunk / 租户 abort | 原测试 | 通过 |

手工/浏览器未做：多轮真实聊天、Skill/Agent/Tool 进度、Evidence、取消后再发、断线、微前端卸载重进。功能协议未改，这些应与修复前一致，但 **待真机确认**。

---

## 8. 仍存在的风险与待验证项

1. **R6 死循环**：已用与用户 SSE 相同的 `#` + ` ` token 序列单测覆盖，并加了解析步数上限。请刷新后再发一条会以标题开头的回复确认页面不再卡死。
2. **累积性能**：R1–R3 仍待 Chrome Performance 对比。
3. **直播气泡**：当前轮的 Markdown 仍每帧解析一次；超长单次回答仍可能掉帧。若仍卡，下一步才是增量 Markdown 或虚拟列表。
4. **antd Collapse**：直播 `AgentExecutionPanel` 未虚拟化。
5. **切会话即 abort**：为隔离状态，正在生成时点开另一会话会取消旧流，不再后台生成。
6. **Wujie alive**：依赖 `__WUJIE_UNMOUNT` → `root.unmount()` → abort。若将来改成停用时不 unmount，需要在 `deactivated` 再 abort。
7. **后端**：未改。token 粒度仍由模型流决定；前端只降 UI 频率。
8. **`skill_resource_loaded` 广播到所有 run**：行为问题，不是这次卡死的主因。

建议真机验证步骤：

1. 同一会话连续 10～20 轮，其中含表格/代码。
2. Chrome Performance：看 Long Task 是否仍随轮次变长。
3. React Profiler：token 期间历史 `ChatMessage` 渲染次数应为 0。
4. 生成中切换会话：Network 中旧 POST 应变 aborted，新列表不再跳动。
5. 停止后再发：不应再出现旧 delta。
6. 从 Shell 离开 Copilot 再进入：不应残留活跃 SSE。

---

## 附录 A. 复现场景对照

| 场景 | 本轮状态 |
| --- | --- |
| 单轮普通聊天 | 静态分析可通过；未真机 |
| 同一会话 10～20 轮 | 成本模型已证实累积；未真机 |
| 长文本流式 | 合帧 + 直播仍每帧解析；未真机 |
| Multi-Agent + Tool + Skill | 控制事件仍同步处理，不丢；未真机 |
| 快速切换历史会话 | 已 abort + 事件守卫；未真机 |
| 中途取消再发送 | 关队列 + abort reader；单测覆盖队列/reader |
| SSE 异常断开 | 无自动重连，不会风暴 |
| 微前端卸载再进 | 源码会 unmount/abort；未真机 |

## 附录 B. Node 基准原始输出

```
[copilot-chat-perf] full=13.62ms isolated=0.99ms ratio=13.80
```

环境：Windows，Vitest 5.0.2，`apps/copilot`，2026-11-25。
