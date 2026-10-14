# Knowledge V5 评测集

本目录配合租户 3 的本地数据集 **V5-RAG-100**。100 道题用于你亲自学习 RAG 评测，而不是让脚本一次跑完。

## 分类

| 分类 | 数量 | 文件 |
| --- | --- | --- |
| ERP 业务（依据实际代码） | 30 | [erp-questions.md](./erp-questions.md) |
| 跨境电商（全文标注为模拟） | 30 | [ecommerce-questions.md](./ecommerce-questions.md) |
| 通用知识 | 30 | [general-questions.md](./general-questions.md) |
| 复杂与边界 | 10 | [advanced-questions.md](./advanced-questions.md) |

所有标准答案均由同一模型/脚本依据文档归纳，**标记为 AI 生成、待人工复核**，不能直接视为独立可靠的生产基准。

## 知识库文档

初始化脚本会上传：

- `services/knowledge/eval_fixtures/docs/erp/`（订单状态机、库存预占、商品采购仓、物流售后 RBAC、异常；另含 `06-parse-sample.pdf` 用于真实 PDF 解析）
- `services/knowledge/eval_fixtures/docs/ecommerce/`（模拟跨境运营与客服）
- `services/knowledge/eval_fixtures/docs/general/`（FastAPI、PostgreSQL/Redis、操作规范、排查）

## 初始化（可重复）

不要把密码写进命令历史以外的文件。PowerShell 示例：

```powershell
$env:KNOWLEDGE_SEED_PASSWORD = "<本地密码>"
$env:KNOWLEDGE_SEED_EMAIL = "123@qq.com"
$env:KNOWLEDGE_SEED_TENANT_ID = "3"
cd services/knowledge
uv run python -m app.scripts.seed_eval_v5
```

脚本会：ERP RSA 登录 → 复用或创建三个知识库 → 上传缺失文档 → 等待 PARSE/CHUNK/EMBED → 按 `external_key` 幂等写入 100 题 → 用真实检索给相关 Chunk 打标 → 只 probe 3 题。

重复执行不会重复插入。缺模型 Key、pgvector 或 Worker 时会失败并说明，不会假装成功。

## 页面入口

登录后打开 Knowledge：`评测数据集` → `V5-RAG-100`。单题评测按钮在每行操作列。完整实验在 `检索评测`。操作说明见 [evaluation-guide.md](./evaluation-guide.md)。抽样真实结果见 [sample-results.md](./sample-results.md)。
