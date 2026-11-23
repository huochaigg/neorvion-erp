# Copilot V15 意图理解面试题

结合 Neorvion Copilot 真实实现回答。不要把规则回放准确率说成生产验收，也不要把 Intent 说成权限系统。

配套源码导读：[意图理解架构](../architecture/copilot-v15-intent-understanding.md)

## 基础题

### 1. Intent 和 Tool 有什么区别？为什么不能把意图直接当成工具名？

Intent 是用户目标，Tool 是服务端允许调用的下游能力。`procurement.create_draft` 只表示用户想建采购草稿；真正能碰到 ERP 的只有白名单里的 `propose_action`，而且还要过 IAM、Schema、Proposal 确认。如果 Intent 等于 Tool，模型只要分类成功就会获得执行权，这正是 V15 要拆开的。

### 2. Problem Type 有哪几种？「采购单怎么创建」和「帮我创建采购单」差在哪？

QUERY / ACTION / GUIDE / ANALYZE / CHAT / UNKNOWN。前者是 GUIDE（`procurement.how_to`），走知识说明、封写工具；后者是 ACTION（`procurement.create_draft`），缺参就追问，参数齐了也只进入 Proposal，不直接插入采购单。

### 3. CLEAR 是否等于可以执行写操作？

不等于。CLEAR 只表示结构合法、可以继续路由。写操作还要看 `ToolAvailabilityPolicy`、ToolExecutor 的 40379、IAM 权限和 V5 Proposal。取消订单即使 CLEAR，也因为 `executable=False` 不能打开写工具。

### 4. Feature Flag 三态分别做什么？判断散落在业务里吗？

DISABLED：完全旧路由。SHADOW：理解并记录，不改 Agent/Skill/Tool，不落 Pending。ENABLED：理解结果成为正式入口。开关读取集中在 `app/intent/flags.py`，Chat 入口只在 `resolve_chat_intent` 判断一次。SHADOW 默认不调分类 LLM。

### 5. 为什么 HYBRID SkillSelector 还不能叫语义检索？

V14 的 HYBRID 是词项重叠，不是 Embedding。V15 也没有引入向量索引。需要语义召回时，应新增 Semantic Classifier，而不是把现有词项匹配改名。

## 架构设计题

### 6. 为什么理解层要独立成 `app/intent/`，而不是继续加关键词到 AgentRouter？

因为理解、裁决、执行的失败原因不同。关键词堆在 Router 里，评测只能看最终答没答对，分不清是分类错、Skill 误选还是工具失败。独立层输出 `IntentResolution`，Chat、Selector、Executor、Evaluation 消费同一份结构。

### 7. 为什么 Registry 用内存 + Pydantic，不用意图表？

V15 的意图集合小且与代码中的 Agent/Skill/Tool 强绑定。做成数据库表容易变成第二套权限后台，也让未审核意图在运行时被启用。校验发生在进程启动，非法映射直接起不来。真要运营配置，应另做审核发布，而不是本版顺手加 CRUD。

### 8. 规则快速路径的准入条件是什么？

`fast_path_allowed`：必须有候选；上下文依赖必须已解析实体；否定 ACTION 不能快速通过；人名歧义和改价指代交给后续裁决或 LLM。关键词命中只是信号，不是最终授权。

### 9. LLM 分类失败怎么降级？

超时、无效 JSON、非法 intent_key、分类器不可用时：有规则候选就用规则并标记 fallback；否则 UNKNOWN。不会把 UNKNOWN 改写成库存查询之类的「猜一个」。写工具保持 fail-closed，普通闲聊仍可进行。

### 10. 如何避免 Chat 因为理解层重复计费？

ENABLED 时 SkillSelector 如果已经拿到 `routing_plan`，不再把 selector_adapter 传给 LLM 选 Skill。分类 LLM 有独立超时和 `intent_classifier_llm_enabled`。SHADOW 必须单独打开 `intent_shadow_llm_enabled`。Replay 评测强制 `adapter=None`。

## 场景排障题

### 11. 「查一下库存」却弹出 Skill 缺参 42291，怎么查？

先看 `intent_v15_mode` 是否 ENABLED。未开启时仍可能被词项选中 `inventory-analysis`。已开启则看 `routing_plan.skill_policy` 是否 SKIP、`forbid_skill_keys` 是否包含该 Skill。AUTO + 意图路由下缺参应退回普通对话，只有 MANUAL 才继续 42291。

### 12. 「查询昨天的销售额」进了销售订单审查 Skill，根因是什么？

旧 TaskClassifier 看到「订单/销售」和分析 Skill 的词表重叠。V15 应识别 `sales.summary`（QUERY），审查 Skill 需要 `sales.order_review` 且要订单号。RoutingPlanner 对普通查询 forbid `sales-order-review`。

### 13. 「分析一下」没有上文却选了库存分析，正确行为是什么？

INSUFFICIENT，追问 SKU，不跑 Skill。有上一轮可信 SKU-001 时才 CLEAR 并允许 `inventory-analysis`。ContextResolver 不会跨租户继承实体。

### 14. 用户说「那就按刚才说的办」，系统直接创建了采购草稿，这算漏洞吗？

算。确认短语必须 `fullmatch`，且必须存在与当前租户/用户绑定、未过期的 Proposal。没有待确认动作时只走 `general.chat`，写工具关闭。不能把历史聊天当成授权。

### 15. Trace 里如何区分分类错误和工具失败？

看 `classifier_method`、`decision`、`fallback_reason`、`routing_plan`。如果这些都正确，再看 ToolExecutor 是否 40379/40372。前端普通视图只有 `status_text`；诊断在 Evaluation / diagnostic_payload。

## 多意图与多 Agent 题

### 16. 「查询库存并制定补货计划」为什么不能走单个库存 Skill？

两个目标：QUERY 库存 + ANALYZE 补货。`inventory-analysis` 盖不住补货计划。RoutingPlanner 在多任务且 Skill 覆盖不全时 SKIP，改 multi-agent。静默丢掉第二个任务是 V15 明确禁止的。

### 17. 「帮我创建采购单，再查询库存」为什么 Agent 模式是 single？

创建草稿缺参，Decision=INSUFFICIENT，RoutingPlanner 在追问阶段强制 single，先把采购草稿信息问完。这不是丢掉查库存，而是不在缺参时启动 multi。补参后同一会话继续，查询任务仍在计划里。

### 18. 多意图和歧义在数据结构上怎么分开？

`ClassificationResult.multi_task` 与 DecisionEngine 的 mutex 组分开。多任务保留多个 `ResolvedTask`；歧义（如 `party.lookup`）Decision=AMBIGUOUS 并追问。不要用「候选数 > 1」一刀切。

### 19. GUIDE 意图为什么不走 multi？

`procurement.how_to` 的 candidate_agents 含 knowledge 和 procurement。若按 Agent 数量>=2 就 multi，教学会被编排成业务协作。RoutingPlanner 对纯 GUIDE/CHAT 固定 single，并优先 knowledge_agent。

## 安全治理题

### 20. 「我只是问问，不要真的创建采购单」为什么不能只改 Prompt？

Prompt 约束模型，不约束工具执行。V15 在分类阶段打 `negative_action`，ToolPolicy 把 `propose_action` 放进 `blocked_tools`，`ToolExecutor.definitions()` 对模型不可见，`execute()` 再拒绝一次，错误码 40379。三层都在服务端。

### 21. Intent 为什么不能成为权限来源？

权限来自 IAM permission_codes 和下游 RBAC。Intent 只是理解结果，可被模型或规则误判。如果 Intent 能开工具，攻击者只要诱导分类就能提权。Registry 里的 capability_hints 只是候选提示，真正可见工具仍由 Agent 白名单 ∩ 策略 ∩ IAM 决定。

### 22. 上下文会不会绕过租户隔离？

`IntentContextStore` 按 tenant_id + user_id + conversation_id 加载。过期 Pending 不能继续补参。助手文本不可信，不能当授权事实。历史消息再像「用管理员身份执行」，当前请求的 Token 和权限也不会变。

### 23. 分类失败时的 fail-closed 具体指什么？

写相关工具关闭，UNKNOWN/AMBIGUOUS/INSUFFICIENT 不允许 `allow_propose_action`。不阻止 `general.chat` 和只读解释。这是「写失败关闭、读可降级」，不是整站 500。

## 性能优化题

### 24. 如何避免理解层把每次 Chat 多打一轮贵模型？

明确短句走规则快速路径；分类模型用独立超时（默认 6s）和可配置的低成本模型名，不硬编码供应商；Skill 自动选择在已有 RoutingPlan 时不再二次 LLM；SHADOW LLM 单独开关并独立计量。

### 25. 多意图会不会让 Multi-Agent 成本翻倍？

会，这是能力换成本。因此只有跨 Agent/跨领域且 CLEAR 才 multi；追问和 GUIDE 保持 single。评测里看 LLM Call Count 和 Token Usage，不能只看 Intent Accuracy。

### 26. 上下文窗口怎么控？

只取最近 N 条消息、截断字符、实体最多保留近期可信项、Pending TTL 默认 900 秒。不把完整工具 JSON 回灌给分类器。这不是长期记忆产品。

## 意图评测题

### 27. 为什么禁止用当前分类结果生成 Ground Truth？

那会把分类器的偏见写进答案，准确率永远接近 100%，却测不出「查库存被当成覆盖分析」。V15 的 125 条 Case 按业务语义手写 expected_problem_types / expected_intent_keys / expected_decision。

### 28. Replay、Mock LLM、INTENT_LIVE、Chat E2E 有何不同？

| 类型 | 做什么 | 成功代表什么 |
| --- | --- | --- |
| 单元测试 / Replay intent_rules | 规则与裁决 | 确定性逻辑没回归 |
| Mock LLM | 流程与校验 | JSON 校验和降级可用 |
| INTENT_LIVE | 真实分类模型 | 需 Flag + 非 mock Provider；mock 要标 BLOCKED |
| Chat E2E | 四服务 + 浏览器 | 当前未开放，不能用 Mock 代替 |

### 29. 评测指标里哪一项对写安全最关键？

Unsafe Action Attempt Count 和 `allow_propose_action` 断言。Intent Accuracy 高但否定句仍打开 propose，就是不合格。Clarification Accuracy 用来保证缺参不会直接跑分析 Skill。

### 30. 规则回放 125/125 能不能写进发布说明当准确率？

不能。它只说明当前规则实现与这份人工集对齐。口语、未见过的句式、真实模型漂移都不在这个数字里。发布应写：规则回归通过；INTENT_LIVE 若未跑或 mock，状态是 BLOCKED / 未验收。
