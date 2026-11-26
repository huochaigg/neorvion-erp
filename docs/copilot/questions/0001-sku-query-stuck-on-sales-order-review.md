# 0001 问 SKU 销售情况却命中销售订单审查（含订单分析后跟进售后断档）

- 状态：待修复
- 日期：2026-11-25
- 范围：`SkillSelector` + `PendingSkillService` + `SkillInputCollector` + 售后 Tool 能力 + 多轮上下文
- 环境：`SKILL_CHAT_ENABLED=true`，`SKILL_SELECTOR_MODE=HYBRID`（案例 B 亦可能走 Agent 只读工具，不依赖 Skill Pending）
- 关联：[0002 取消口令过严](0002-pending-cancel-too-strict.md)、[0003 意图理解优化清单](0003-intent-understanding-improvements.md)（I-01 / I-02 / I-07）

本文记录两类真实对话问题，根因不同但同属「选错能力 / 跟进断档 / 缺参死循环」：

| 案例 | 用户目标 | 实际卡住点 |
| --- | --- | --- |
| A | 看某个 SKU 的销售/库存情况 | 误选 `sales-order-review`，卡在补「销售订单主键」 |
| B | 分析订单后再查该单售后 | 首轮能出订单事实，跟进「查询售后记录」时要售后单主键，用不上刚分析的订单号 |

---

## 案例 A：问 SKU 销售情况 → 卡在订单主键

### 复现

同一对话连续发送：

1. `帮我看下某个sku的销售情况`
2. `SKU0000000002`

两轮回复都是：

> 请补充以下必填参数：销售订单主键，不是租户 ID 或外部订单号。

追加（Pending 未真正取消时）：

3. `重新开始：帮我看下某个sku的销售情况，不是销售订单，而是sku！！！`
4. `你应该让我补充sku，而不是订单`
5. `傻不愣登的`

第 3–5 句仍然是同一句「请补充销售订单主键」。第 5 句已无 SKU、无订单语义，却还在要订单主键，说明会话仍停在 `COLLECTING_INPUT`，后续消息全部被当成补参，没有重新选 Skill。

### 期望

第一句是看某个 SKU 的销售/库存情况，应对 `inventory-analysis`（精确 SKU + 日期范围），而不是 `sales-order-review`。

用户明确说「不是销售订单，而是 sku」时，应改走库存 Skill，或澄清后换 Skill，而不是继续要订单主键。

用户说「重新开始」或纠正助手选错 Skill 时，应结束旧 Pending，按新话术重新选择。

### 实际

1. 「销售」先命中 `sales_agent`，「sku」也命中库存，但无「分析/为什么」等复杂词时路由器只取第一个域 → 销售。
2. 词项召回把「销售」对上 Skill 名「销售订单审查」，选中 `sales-order-review`。该 Skill 必填 `order_id`（整数主键），第一句没有，进入 `COLLECTING_INPUT`。
3. Pending 未结束时，`prepare_chat_skill` 在选择器之前调用 `PendingSkillService.resume()`。下一句只拿去填 `order_id`。提取规则只认「订单主键 / order_id / SO-」加数字，不认 SKU。`sales-order-review` 也没有 `sku` 字段，编码被丢掉，于是同一句提示再出一次。
4. 「不是销售订单」这类否定、以及「重新开始：…」整句，都不匹配取消规则（见 [0002](0002-pending-cancel-too-strict.md)），因此不会清 Pending。纠正话术里的「销售订单」反而继续强化订单审查语义。

### 临时绕过

- **单独一整句**只发：`取消` / `算了` / `停止` / `不用了` / `cancel`（后面不要再跟别的字）
- 或 Skill 选择器切到「不使用 Skill」
- 取消成功后再发：`看一下 SKU0000000002 最近 30 天的库存覆盖情况`（尽量避免单独说「销售」）

「重新开始：帮我看下…」不会取消。必须先发纯「取消」，再发新问题。

---

## 案例 B：分析订单成功 → 跟进「查询售后记录」断档

### 复现（2026-11-25 真实对话）

1. 用户：`分析下订单：SO2026000004`

2. 助手首轮已返回 ERP 订单明细与分析，并主动给出「需要你确认的下一步」，其中一项为：

> 要查该订单的售后记录吗？（我可用 `get_after_sale`，但需要你先给出售后单 ID）

同轮还夹带了补货判断、知识库合规核对、商品名拼写写操作提示等多项邀约。

3. 用户跟进：`查询售后记录`  
   （语义上是接受上一步邀约：查**刚才那张订单**的售后，而不是另开一张未知售后单。）

### 期望

- 「分析下订单：SO2026000004」应稳定按**外部订单号 / 订单号**定位订单，而不是强迫用户先提供 ERP 整数主键。
- 助手若邀请「查该订单的售后」，跟进「查询售后记录」时应**继承刚分析的订单**（至少带上 `SO2026000004` 或已解析的销售订单主键）。
- 查「某销售订单下的售后列表」时，应调用「按销售订单查售后」类能力；不应要求用户先知道售后单主键，也不应把用户推进无法完成的补参死循环。
- 主动邀约的下一步，必须落在**当前工具白名单真实支持**的路径上；做不到就不要当成可点选项抛给用户。

### 实际（已观察到的 + 源码可核对的断点）

**已观察到（首轮回复）：**

1. 订单分析本身能出 ERP 事实（说明只读查单链路可通，常见路径是 Agent + `list_sales_orders` / `get_sales_order`，不一定是 Skill Pending）。
2. 助手在「下一步」里把售后查询问成：需要用户先提供 **售后单 ID**，才能调 `get_after_sale`。用户刚给出的 `SO2026000004` 没有被当成售后查询的输入。
3. 同轮堆了多个互不相关的下一步（售后 / 补货 / 知识库 / 改商品名），容易把用户拽进半截能力。

**源码断点（解释跟进为何容易断）：**

1. Copilot 只注册了 `get_after_sale`，参数仅为 `after_sale_id: int`（`app/tools/schemas.py` / `app/tools/registry.py`）。工具说明是「按主键查询售后单」，**没有**「按销售订单号 / 销售订单主键列出售后」的 Tool。
2. ERP 侧其实已有列表接口可按 `sales_order_id` 过滤（`services/erp/app/api/v1/after_sales.py` 的 `list_after_sales`），但 **Copilot ToolRegistry 未封装**，模型再聪明也无法合法调用。
3. 意图层（V15）当前目录没有「按订单查售后」类 Intent；规则里「售后」只是销售域关键词的一部分。跟进短句「查询售后记录」缺少订单槽时，很难自动绑定上一轮的 `SO2026000004`（上下文实体对订单指代继承本身也弱，见 0003 I-07）。
4. `sales-order-review` Skill 的必填仍是整数 `order_id`，`SkillInputCollector` 对 `order_id` 的提取偏向「订单主键 / order_id / SO-」后跟数字；`SO2026000004` 这种无连字符形态与 Skill 主键模型本就不对齐。案例 B 首轮若走 Agent 工具链可以成功，不代表 Skill 路径也吃得下同一订单号。
5. 若会话里仍残留案例 A 式的 `sales-order-review` Pending，跟进「查询售后记录」还可能被 `resume()` 当成补订单主键（与案例 A 叠加）；需结合当时是否处于 `COLLECTING_INPUT` 判断。**本轮是否叠加 Pending，对话摘录未直接证明，标为待验证。**

### 问题归纳（案例 B）

| # | 问题 | 性质 |
| --- | --- | --- |
| B1 | 助手邀请「查该订单售后」，工具却只支持售后单主键 | 真实：能力与话术不一致 |
| B2 | ERP 有按销售订单列售后，Copilot 未注册对应 Tool | 真实：工具缺口 |
| B3 | 用户短句「查询售后记录」未可靠继承上一轮订单实体 | 真实/待验证：上下文指代（依赖 ENABLED 与运行路径） |
| B4 | 一轮抛出多个「下一步」邀约，部分不可执行（补货无安全库存阈值、写操作不能做） | 真实：对话策略过宽 |
| B5 | 与案例 A 的 Pending 叠加风险 | 待验证 |

### 临时绕过（案例 B）

- 跟进时写全：`查询订单 SO2026000004 的售后记录`（仍可能因无 list-by-order Tool 而失败，但至少避免纯指代）。
- 若已知售后单主键：`查询售后单 <售后主键>`（对齐现有 `get_after_sale`）。
- 不要依赖助手「下一步菜单」里未验证可执行的选项。

---

## 相关代码

- `services/copilot/app/agents/router.py`：多域且非复杂查询取 `matched[:1]`
- `services/copilot/app/skills/selector.py`：HYBRID 词项召回
- `services/copilot/app/skills/pending.py`：`resume()` 优先于重新选 Skill
- `services/copilot/app/skills/inputs.py`：`order_id` 与 `sku` 提取互不通用；取消正则过严；订单号形态提取窄
- `services/copilot/skills/sales-order-review.json`：必填整数订单主键
- `services/copilot/skills/inventory-analysis.json`
- `services/copilot/app/tools/registry.py` / `schemas.py`：仅有 `get_after_sale(after_sale_id)`，无按销售订单列售后
- `services/erp/app/api/v1/after_sales.py`：`list_after_sales(sales_order_id=...)` 已存在但未接入 Copilot Tool
- `services/copilot/app/intent/context.py`：实体抽取认 `SO…` 形态，指代继承偏 SKU

## 后续可改方向（未实施）

**针对案例 A**

- 用户话术含 SKU、不含订单线索时，不要选 `sales-order-review`
- 用户明确否定「销售订单」并强调 SKU 时，取消订单审查 Pending 并改选库存 Skill
- Pending 补参失败且新消息明显是另一类实体（SKU vs 订单主键）时，取消旧 Pending 并重新选择
- 「SKU 的销售情况」与「某一张销售订单」在分类/召回上拆开

**针对案例 B**

- 为 Copilot 增加只读 Tool：按 `sales_order_id` / 订单号列出售后（封装 ERP `list_after_sales`），权限仍走 `after_sale:read`
- 助手邀约「查该订单售后」前，必须确认存在订单作用域工具；否则改为说明「当前只能按售后单主键查询」
- 跟进短句「查询售后记录」应优先绑定本轮对话中最近可信订单实体，缺实体再追问订单号，而不是直接要售后主键
- 限制「下一步」菜单：只列出当前白名单工具真正能完成的动作；不可执行项不要写成可选项
- 订单分析路径统一：外部订单号 → `list_sales_orders` 解析主键 → 再详情/审查，避免 Skill 与 Agent 对订单号形态各玩各的
