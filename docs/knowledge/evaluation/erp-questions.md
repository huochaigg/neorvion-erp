# ERP 业务评测题（30）

标注状态：AI 生成、待人工复核。无答案题已标 expected_no_answer。

## erp-001

- 问题：销售订单 DRAFT 状态会不会预占库存？
- 标准答案：不会。DRAFT 可改明细，未预占库存。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md
- Chunk 线索：DRAFT, 未预占（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：order, inventory
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-002

- 问题：确认销售订单时扣减的是 quantity 还是只做预占？
- 标准答案：确认只写 RESERVE，增加 reserved_quantity，不扣减 quantity。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md, 02-inventory-reserve.md
- Chunk 线索：RESERVE, 确认（导入后关联真实 Chunk ID）
- 难度：2　类型：MULTI_CONDITION　有答案：是
- 标签：order, reserve
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-003

- 问题：待出库订单还能整单取消吗？取消时库存怎么处理？
- 标准答案：可以。WAITING_OUTBOUND 属于可取消集合，整单取消会 RELEASE 预占。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md
- Chunk 线索：WAITING_OUTBOUND, 取消（导入后关联真实 Chunk ID）
- 难度：2　类型：MULTI_CONDITION　有答案：是
- 标签：cancel
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-004

- 问题：已经部分出库的销售订单能否整单取消？
- 标准答案：不能。PARTIALLY_OUTBOUND 已经扣过库存，不能整单取消。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md
- Chunk 线索：PARTIALLY_OUTBOUND, 不能整单取消（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：cancel
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-005

- 问题：可用库存在数据库里是哪一列？
- 标准答案：没有单独列。可用库存 = quantity - reserved_quantity。
- 知识库：ERP业务知识库
- 来源文档：02-inventory-reserve.md
- Chunk 线索：可用库存, quantity - reserved（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：inventory
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-006

- 问题：库存维度是 SKU 全局一个数字吗？
- 标准答案：不是。维度是 Tenant + Warehouse + SKU。
- 知识库：ERP业务知识库
- 来源文档：02-inventory-reserve.md
- Chunk 线索：Tenant + Warehouse + SKU（导入后关联真实 Chunk ID）
- 难度：2　类型：PARAPHRASE　有答案：是
- 标签：inventory, warehouse
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-007

- 问题：销售出库时 quantity 和 reserved_quantity 怎么变？
- 标准答案：OUTBOUND 同时减少 quantity 和 reserved_quantity。
- 知识库：ERP业务知识库
- 来源文档：02-inventory-reserve.md
- Chunk 线索：OUTBOUND, quantity, reserved（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：outbound
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-008

- 问题：释放预占超过 reserved_quantity 会怎样？
- 标准答案：返回 INSUFFICIENT_RESERVED_INVENTORY。
- 知识库：ERP业务知识库
- 来源文档：02-inventory-reserve.md
- Chunk 线索：INSUFFICIENT_RESERVED_INVENTORY（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：exception
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-009

- 问题：盘点调整和预占冲突时错误码是什么？
- 标准答案：STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY。
- 知识库：ERP业务知识库
- 来源文档：02-inventory-reserve.md
- Chunk 线索：STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：stocktake
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-010

- 问题：待确认订单确认成功后进入什么状态？
- 标准答案：WAITING_OUTBOUND。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md
- Chunk 线索：PENDING_CONFIRMATION, WAITING_OUTBOUND（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：order
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-011

- 问题：销售预占流水用什么 reference 区分来源订单？
- 标准答案：SALES_ORDER。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md
- Chunk 线索：SALES_ORDER（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：inventory
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-012

- 问题：库存预占落在 SPU 还是 SKU？
- 标准答案：落在 SKU，不落在 SPU。
- 知识库：ERP业务知识库
- 来源文档：03-product-purchase-warehouse.md
- Chunk 线索：SKU, 库存（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：product
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-013

- 问题：采购退货审核通过后停留在 APPROVED 吗？
- 标准答案：不停留。同事务进入 WAITING_OUTBOUND。
- 知识库：ERP业务知识库
- 来源文档：03-product-purchase-warehouse.md
- Chunk 线索：WAITING_OUTBOUND, 采购退货（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：purchase-return
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-014

- 问题：仓库调拨会写哪些库存流水类型？
- 标准答案：TRANSFER_OUT 和 TRANSFER_IN。
- 知识库：ERP业务知识库
- 来源文档：03-product-purchase-warehouse.md
- Chunk 线索：TRANSFER_OUT, TRANSFER_IN（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：transfer
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-015

- 问题：系统现在会按渠道自动选择最优仓发货吗？
- 标准答案：不会。建议中的规则，当前以指定仓库为准。
- 知识库：ERP业务知识库
- 来源文档：03-product-purchase-warehouse.md
- Chunk 线索：建议, 未作为强制（导入后关联真实 Chunk ID）
- 难度：3　类型：HALLUCINATION　有答案：是
- 标签：suggested
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-016

- 问题：部分交给承运商和全部交给承运商分别是什么订单状态？
- 标准答案：PARTIALLY_SHIPPED 与 SHIPPED。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md
- Chunk 线索：PARTIALLY_SHIPPED, SHIPPED（导入后关联真实 Chunk ID）
- 难度：2　类型：MULTI_CONDITION　有答案：是
- 标签：shipping
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-017

- 问题：订单 COMPLETED 的条件是什么？
- 标准答案：全部物流单都已签收。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md
- Chunk 线索：COMPLETED, 签收（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：shipping
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-018

- 问题：退货入库写哪种库存流水？
- 标准答案：RETURN_INBOUND。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md
- Chunk 线索：RETURN_INBOUND（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：aftersale
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-019

- 问题：退款成功是否等于库存已经加回？
- 标准答案：不等于。退款与退货状态独立。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md
- Chunk 线索：退款, 库存已加回（导入后关联真实 Chunk ID）
- 难度：2　类型：PARAPHRASE　有答案：是
- 标签：refund
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-020

- 问题：前端传入的 X-Tenant-Id 能单独作为租户权威吗？
- 标准答案：不能。只是意愿，必须经成员关系校验。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md
- Chunk 线索：X-Tenant-Id, 意愿（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：tenant
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-021

- 问题：Knowledge 复用哪一组 ERP 权限码？
- 标准答案：knowledge:read/create/update/delete。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md
- Chunk 线索：knowledge:read（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：rbac
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-022

- 问题：能否从草稿直接出库？
- 标准答案：不能。必须先到 WAITING_OUTBOUND。
- 知识库：ERP业务知识库
- 来源文档：05-exceptions.md
- Chunk 线索：不能跳过确认（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：order
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-023

- 问题：模拟案例里确认 2 件后 quantity 和 reserved 分别是多少（原 quantity=10）？
- 标准答案：quantity 仍为 10，reserved_quantity 变为 2，可用 8。该段标明为模拟案例。
- 知识库：ERP业务知识库
- 来源文档：05-exceptions.md
- Chunk 线索：模拟案例, reserved_quantity 变为 2（导入后关联真实 Chunk ID）
- 难度：3　类型：MULTI_CONDITION　有答案：是
- 标签：case
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-024

- 问题：OUTBOUNDED 表示已经交给承运商了吗？
- 标准答案：没有。表示购买数量已离开库存账面，尚未全部交给承运商。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md
- Chunk 线索：OUTBOUNDED, 承运商（导入后关联真实 Chunk ID）
- 难度：3　类型：PARAPHRASE　有答案：是
- 标签：order
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-025

- 问题：采购入库增加的是 reserved 还是 quantity？
- 标准答案：INBOUND 增加 quantity。
- 知识库：ERP业务知识库
- 来源文档：02-inventory-reserve.md
- Chunk 线索：INBOUND, 采购入库（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：purchase
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-026

- 问题：不同租户可以有相同 SKU 编码吗？
- 标准答案：可以。查询始终带 tenant_id。
- 知识库：ERP业务知识库
- 来源文档：03-product-purchase-warehouse.md
- Chunk 线索：跨租户, 相同编码（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：tenant, sku
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-027

- 问题：Knowledge 是否自己再建一套用户表？
- 标准答案：否，复用 ERP 用户与权限。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md
- Chunk 线索：不另建用户表（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：rbac
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-028

- 问题：待确认阶段取消订单会不会动库存？
- 标准答案：不会。确认前取消不动库存。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md
- Chunk 线索：PENDING_CONFIRMATION, 不动库存（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：cancel
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-029

- 问题：请按顺序说明：提交、确认、出库三步各自对库存做什么？
- 标准答案：提交到待确认仍不预占；确认 RESERVE；出库 OUTBOUND 扣 quantity 与 reserved。
- 知识库：ERP业务知识库
- 来源文档：01-sales-order-state.md, 02-inventory-reserve.md, 03-product-purchase-warehouse.md, 04-shipping-aftersale-rbac.md, 05-exceptions.md
- Chunk 线索：RESERVE, WAITING_OUTBOUND, OUTBOUND（导入后关联真实 Chunk ID）
- 难度：4　类型：LONG　有答案：是
- 标签：flow
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## erp-030

- 问题：访问其他租户订单时，系统如何避免泄露资源是否存在？
- 标准答案：返回 404 或 403，不泄露是否存在。
- 知识库：ERP业务知识库
- 来源文档：05-exceptions.md
- Chunk 线索：404, 不泄露（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：tenant
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____
