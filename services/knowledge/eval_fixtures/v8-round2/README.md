# V8 第二轮：多 Chunk 测试语料

本目录存放 V8 第二轮语料与 120 题综合评测工作稿。

语料已导入租户 3 知识库 **#8 `V8-R2-Multi-Chunk`**（8 份 Markdown，80 ACTIVE Chunk）。题目工作稿导入数据集 **`V8-R2-120-Comprehensive`**（#10），全部 `needs_human_review=True`，未冻结。

重复导入：

```text
uv run python -m app.scripts.import_v8_r2_120 --dry-run
uv run python -m app.scripts.import_v8_r2_120
```

只读写评测题和确定性标注，不调用 Embedding / Chat / Judge / Rerank，不修改知识库 #7 与 Run 39～42。

## 为什么不能写入知识库 #7

租户 3 知识库 **#7「测试知识库」** 当前 13 个 ACTIVE 切片，对应 V8-01～V8-07 的 25 道已复核冻结题，以及 Run 39～42 基线。该库没有独立的「语料版本」字段：往里面加文档会改变检索候选池，历史 Run 虽钉住数据集版本，但新检索会混入第二轮正文。

第二轮应新建独立知识库，例如：

| 项 | 建议 |
| --- | --- |
| 名称 | `V8-R2-Multi-Chunk` |
| 租户 | 与 #7 相同的测试租户 |
| 授权 | 仅测试成员；不要写入正式库 |
| 切片 | 导入时再选；对照实验用默认 `RECURSIVE` 800 / 120 |
| 旧库 #7 | 只读，不上传、不重建、不删除 |

创建知识库、上传、切片、Embedding 都等语料确认后再做。

## 切分算法（本地预估所用）

与线上一致：`app/processing/split.py` + `app/core/config.py`。

- 长度单位：Python `len`（字符），不是 Token
- 默认策略：`RECURSIVE`
- 默认 `chunk_size=800`，`chunk_overlap=120`（重叠必须小于切片长度）
- 分隔符：空行 → 换行 → `。！？；，` → 空格 → 按字符
- 合法范围：100–8000

本地预估见 `chunk-estimate.json`。默认 800/120 合计 **80** 个切片，落在 80～150 目标下限。未上传，因此还没有数据库里的有效 Chunk。

## 本轮不做的事

- 不修改知识库 #7、13 个 Chunk、V8-01～V8-07 冻结版本、Run 39～42
- 不修改检索、Rerank、评测算法
- 不自动生成或冻结新题目
- 不执行 git add / commit / push / tag

确认语料后再进行智能标注。

## 第二轮隔离实验建议（先不要创建或运行）

导入独立库并完成切片、Embedding 之后，再人工确认语料，再智能标注。建议实验全部钉住同一数据集版本，且只关联新库：

1. **切片消融**：同一批 Markdown，分别用 `RECURSIVE` 400/60、800/120、1600/200 建三套切片版本（或三本子库），比较精确错误码与跨章节规则的 Recall。400 会超过 150 片，只作压力组。
2. **策略 A/B**：VECTOR / KEYWORD / HYBRID / HYBRID+Rerank，Top-K 仍为 8。把 `candidate_k` 从 24 提到 32 或 48，否则 80 片里只有 24 个候选，和第一轮「候选覆盖全库」不可比。
3. **Evidence Coverage**：等标注完成后再算「一道题的多段证据是否同时进入 Top-K」。当前 `metrics.py` 没有该列，不要改算法抢先实现。
4. **对照第一轮**：Run 39～42 仍留在知识库 #7。不要把第二轮 Run 写进同一实验以免列表混淆；新建实验组即可。

生成评测默认关闭。未经明确要求不要启动付费 Embedding 或 Judge。
