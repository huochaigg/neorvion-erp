# V8 诊断题包

这些文件由 `uv run python -m app.scripts.v8_pack` 从 `app/evaluation/v8_catalog.py` 写出。

不会在应用启动、数据库迁移或本命令中上传知识库、写入评测表或调用模型。

## 与原始 100 题的关系

`V8-00-Baseline` 不是新数据集。请继续使用已经冻结的原始评测集，不要覆盖它的题目、标注或历史 Run。

本目录只新增 V8-01 到 V8-07。题目全部 `needs_human_review=true`，没有 Chunk 标注，因此不能直接当 READY Ground Truth。

## 导入

1. 新建一个专用测试知识库，不要把这些文档上传进正式知识库。
2. 用现有文档上传接口导入 `docs/`。等待 PARSE、CHUNK、EMBED 完成。
3. 为每个 `questions.json` 里的 `dataset` 新建评测数据集，并只关联这个测试库。
4. 用现有 `external_key` 幂等导入题目。重复导入应更新而不是复制。
5. 对照 `evidence_quote` 人工标注相关 Chunk。确认后再把题目标为可评测。无答案题不要因为某次检索为空就标成无答案；目录里的无答案题已经对照指定文档检查过证据不足。
6. 冻结数据集版本。
7. 用 `experiment-presets.json` 创建 VECTOR、KEYWORD、HYBRID、HYBRID+Rerank 四组实验。创建时不要自动运行。生成评测保持关闭。

`manifest.json` 的 `imported` 固定为 false，表示仓库里的文件尚未入库。
