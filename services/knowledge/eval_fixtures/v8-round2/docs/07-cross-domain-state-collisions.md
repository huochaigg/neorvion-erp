# 跨领域相似状态与错误码对照

本文把销售、采购、调拨、售后里容易撞车的英文标识放到同一份文档里，便于后续做相似状态检索和精确标识评测。每一条都能回到对应领域文档和源码，不引入新规则。

## 三种 DRAFT

| 单据 | 状态 | 保存草稿时库存 | 下一步真正改库存的动作 |
| --- | --- | --- | --- |
| 销售订单 | `DRAFT` | 未预占 | 确认订单：增加 `reserved_quantity` |
| 采购单 | `DRAFT` | 未入库 | 确认收货：增加 `quantity` |
| 调拨单 | `DRAFT` | 不改。库存不足也可保存 | 确认调出：减少源仓 `quantity` |
| 采购退货 | `DRAFT` | 不占用可退、不改库存 | 确认退货出库：减少 `quantity` |
| 出库单 | 无 DRAFT，创建即为 `PENDING_PICKING` | 仍是销售预占 | 确认出库：同时减少 `quantity` 与 `reserved` |
| 收货单 | `DRAFT` | 不改 | 确认收货：增加 `quantity` |

「草稿不改库存」在多个章节成立，但下一步动作完全不同。检索命中「DRAFT 不改库存」时，必须看它属于哪张单据。

## 三种等待出库

| 单据 | 英文标识 | 到达该状态时库存已经怎样 | 取消 |
| --- | --- | --- | --- |
| 销售订单 | `WAITING_OUTBOUND` | 已经预占 | 可以整单取消并释放预占 |
| 调拨单 | `PENDING_OUTBOUND` | 尚未扣源仓 | 可以取消，仍不改库存 |
| 采购退货 | `WAITING_OUTBOUND` | 已占用可退数量，尚未扣库存 | 视实现中的取消规则；扣库存发生在退货出库确认 |

销售 `WAITING_OUTBOUND` 和采购退货 `WAITING_OUTBOUND` 字符串相同。调拨用的是 `PENDING_OUTBOUND`。不要用「待出库」三个汉字把三者合成一条库存规则。

销售部分出库后的状态是 `PARTIALLY_OUTBOUND`，已经扣过库存，不能整单取消。采购部分收货是 `PARTIALLY_RECEIVED`。采购退货部分出库是 `PARTIALLY_RETURNED`。售后退货部分收货是 `PARTIALLY_RECEIVED`。后两个「部分收货」一个在采购正向、一个在销售退货，单据不同。

## 三种「确认」

| 动作 | 权限 | `quantity` | `reserved_quantity` |
| --- | --- | --- | --- |
| 销售订单确认 | `order:audit` | 不变 | 增加 |
| 采购单批准 | `purchase:audit` | 不变 | 不变 |
| 采购收货确认 | `purchase:receipt:confirm` | 增加 | 不变 |
| 销售出库确认 | `outbound:confirm` | 减少 | 减少 |
| 调拨确认调出 | `stock_transfer:outbound` | 源仓减少 | 不变 |
| 调拨确认调入 | `stock_transfer:receive` | 目标仓增加 | 不变 |
| 退货入库确认 | `return_order:inbound` | 增加（仅 `GOOD`） | 不变 |
| 采购退货出库确认 | `purchase_return:outbound` | 减少 | 不变 |
| 物流确认发货 | `shipment:confirm` | 不变 | 不变 |

同一结论「确认不改 quantity」至少出现在：销售订单确认、采购批准、物流确认发货。同一结论「确认才增加 quantity」出现在：采购收货、调拨调入、销售退货良品入库。评测时必须指定是哪一种确认。

## 错误码家族

| 错误码 | 服务 | 含义 |
| --- | --- | --- |
| `INSUFFICIENT_AVAILABLE_INVENTORY` | `inventory.py` / 销售确认 / 调拨 / 采购退货出库 | 可用库存不够 |
| `INSUFFICIENT_RESERVED_INVENTORY` | `inventory.py` 释放路径 | 释放数量超过 `reserved_quantity` |
| `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY` | `inventory.py` 盘点 | 调整后会打破预占不超过实际 |
| `OUTBOUND_EXCEEDS_RESERVED` | `outbound.py` | 出库超过该订单已预占 |
| `OUTBOUND_PICK_EXCEEDS_PLAN` | `outbound.py` | 拣货超过本张出库单计划 |
| `SHIPMENT_EXCEEDS_OUTBOUND` | `shipment.py` | 发货超过已出库 |
| `PURCHASE_RECEIPT_EXCEEDS_REMAINING` | `purchase_receipt.py` | 收货超过未收完数量 |
| `PURCHASE_RETURN_EXCEEDS_RETURNABLE` | `purchase_return.py` | 采购退货超过已收可退 |
| `PURCHASE_RETURN_OUTBOUND_EXCEEDS_REMAINING` | `purchase_return_outbound.py` | 本次退货出库超过剩余批准 |
| `AFTER_SALE_EXCEEDS_RETURNABLE` | `after_sale.py` | 售后超过已出库可退 |
| `AFTER_SALE_EXCEEDS_REFUNDABLE` | `after_sale.py` | 售后超过可退金额 |
| `REFUND_EXCEEDS_APPROVED` | `refund.py` | 退款超过批准剩余 |
| `SUPPLIER_REFUND_EXCEEDS_APPROVED` | `supplier_refund.py` | 供应商退款超过批准 |

这些字符串必须精确检索。同义改写成「库存不够」或「超出预占」不足以区分路径。

英文标识速查（源码中的字面量）：

- `SalesOrderStatus` 包括 `PARTIALLY_OUTBOUND` 和 `WAITING_OUTBOUND`
- 出库超额：`OUTBOUND_EXCEEDS_RESERVED`
- 释放超额：`INSUFFICIENT_RESERVED_INVENTORY`
- IAM 知识库读取：`knowledge:read`
- 售后类型：`REFUND_ONLY` / `RETURN_AND_REFUND` / `RETURN_ONLY`
- 退货质量：`GOOD` / `DAMAGED` / `UNSELLABLE` / `OTHER`

中英混合提问时，仍应命中上述标识，而不是同义改写后的中文状态名。

## 同一结论出现在多个章节

下列句子在本语料的不同文档里用不同上下文重复，这是有意设计的多段证据，不是复制填充。

1. 销售订单 `DRAFT` 未预占库存。出现在销售文档的状态表，也出现在本对照的 DRAFT 表。
2. 采购单审核通过不改库存；收货确认才增加 `quantity`。出现在采购文档，也出现在本对照的确认表。
3. 调拨从 `DRAFT` 提交到 `PENDING_OUTBOUND` 仍然不改库存。出现在库存调拨文档，也出现在本对照的等待出库表。
4. 可用库存 = `quantity - reserved_quantity`，不单独落库。出现在库存文档，也约束调拨和采购退货「只能动 available」。
5. 评测指标由代码计算，禁止用 LLM 给 Recall 打分。只写在知识库评测文档；本对照不重复展开，避免把评测规则误写成 ERP 库存规则。

单个问题如果问「确认会不会改库存」，必须同时看到是哪一种确认，单靠一个章节的「确认」二字不够。

## 明确不存在的能力

下列内容不得当成 Ground Truth，因为当前源码没有实现：

- 销售订单状态里没有 `FAST_WAREHOUSE_TIMEOUT`
- 出库服务没有 `MAGIC_STOCK_OVERFLOW`
- 采购单没有单独 `APPROVED`
- 内部 SSO 不是 OIDC
- 关键词检索不是 BM25
- 当前向量检索不建 HNSW
- 换货重新发货未做
- 调拨第一版不处理运输损耗，也没有独立在途库存表
- 残次品没有单独库存台账

若后续评测需要无答案题或抗噪声题，应单独标记 SYNTHETIC，不要把本节的「不存在」清单改成肯定答案。

## 单号前缀

编号都在 flush 拿到 id 后生成，租户内唯一，不用 `MAX+1`。不同企业可以出现不连续的序号。

| 前缀 | 单据 |
| --- | --- |
| `SO` | 销售订单 |
| `OUT` | 销售出库单 |
| `PO` | 采购单 |
| `PR` | 采购收货单 |
| `PRT` | 采购退货单 |
| `PRO` | 采购退货出库单 |
| `SRF` | 供应商退款 |
| `TR` | 调拨单 |
| `AS` | 售后单 |
| `RT` | 销售退货单 |
| `CUS` | 客户编码（若未手填） |
| `SHP` | 物流单 |
| `ST` | 盘点单 |
| `CAR` | 物流商编码（若未手填） |

问「OUT 和 PRT 哪一个会扣销售预占」时：`OUT` 确认出库同时减 `quantity` 和 `reserved`；`PRT`/`PRO` 只减 `quantity`，不释放销售预占。`SHP` 确认发货不改库存。`ST` 确认盘点才按差异改 `quantity`。

## 权限同名审核

| 权限 | 单据动作 | 库存 |
| --- | --- | --- |
| `order:audit` | 销售确认 | 预占 |
| `purchase:audit` | 采购批准 | 不改 |
| `purchase:receipt:confirm` | 收货确认 | 加 `quantity` |
| `outbound:confirm` | 销售出库确认 | 减 `quantity` 与 `reserved` |
| `stock_transfer:outbound` | 调拨调出 | 减源仓 `quantity` |
| `stocktake:confirm` | 盘点确认 | 按差异调整，可能与预占冲突 |
| `refund:confirm` | 确认外部退款 | 不改库存 |
| `knowledge:update` | 重建索引、模型连通 | 不改 ERP 库存 |

「audit」和「confirm」在权限名里反复出现。检索必须连权限码一起看，不能只看中文「审核通过」。

## 两种 IN_TRANSIT 与 40097

物流单 `IN_TRANSIT`：包裹在承运商手里，库存早已在出库时扣过。调拨单 `IN_TRANSIT`：源仓已扣 `quantity`，目标仓未加。轨迹事件里也有 `IN_TRANSIT`，那是承运商节点，不是调拨状态。

业务码 `40097` 出现在：

- 销售订单：停用仓，`WAREHOUSE_DISABLED`
- 采购单 / 调拨 / 盘点 / 售后：仓库未启用，中文消息不同
- 物流商：状态或类型不合法

`40097` 不是唯一的「仓库停用」标识码。精确字段题应优先用 `data.error` 字符串或完整中文消息，而不是只搜数字码。

`SHIPMENT_ALREADY_CONFIRMED` 与 `STOCKTAKE_ALREADY_CONFIRMED`、`PURCHASE_RECEIPT_ALREADY_CONFIRMED`、`STOCK_TRANSFER_ALREADY_OUTBOUND` 都表示「这张单已经确认过，不要再改库存或再累加一次」。命中其中一个不能当作另一个单据的证据。

## 多段证据题应该怎么拆

下列问题在后续标注时预计需要跨文档取证，现在只作为语料设计说明，不在本轮生成题目。

1. 「确认会不会改库存」：必须同时看到销售确认、采购批准、收货确认、出库确认、发货确认中的至少两类。
2. 「INSUFFICIENT_ 开头的错误码有何不同」：可用不足、预占释放不足、盘点预占冲突要分章。
3. 「WAITING_OUTBOUND 能不能取消」：销售可以释放预占；采购退货同名状态扣库存发生在出库确认；采购正向待收货反而不可取消。
4. 「knowledge:read 是否等于能读任意知识库」：IAM 功能权限加上 Knowledge ACL grants。
5. 「SHIPPED 是仓库出库还是物流发货」：V9 之后销售订单 `SHIPPED` 表示已交给承运商；出库完成是 `OUTBOUNDED`。

同一结论在领域文档和本对照文档各出现一次，是为了测 Coverage，不是为了凑切片数。

`inventory:outbound` 与 `outbound:confirm` 同时出现在权限目录里。真正扣销售库存的是后者。`inventory:inbound` 与 `purchase:receipt:confirm` 同理。检索「inbound 权限」时不要把预留编码当成收货确认所需权限。

