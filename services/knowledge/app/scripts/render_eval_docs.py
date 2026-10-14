"""把 100 道题渲染进 docs/knowledge/evaluation。"""

from __future__ import annotations

from pathlib import Path

from app.scripts.eval_questions import all_questions

_ROOT = Path(__file__).resolve().parents[4] / "docs" / "knowledge" / "evaluation"
_GROUPS = {
    "erp": ("erp-questions.md", "ERP 业务评测题（30）"),
    "ecommerce": ("ecommerce-questions.md", "跨境电商评测题（30，模拟）"),
    "general": ("general-questions.md", "通用知识评测题（30）"),
    "advanced": ("advanced-questions.md", "复杂与边界评测题（10）"),
}


def main() -> None:
    items = all_questions()
    if len(items) != 100:
        raise SystemExit(f"题目数量应为 100，实际 {len(items)}")
    _ROOT.mkdir(parents=True, exist_ok=True)
    for category, (filename, title) in _GROUPS.items():
        rows = [item for item in items if item["category"] == category]
        lines = [f"# {title}", "", "标注状态：AI 生成、待人工复核。无答案题已标 expected_no_answer。", ""]
        for item in rows:
            answer_flag = "否（expected_no_answer）" if item["is_unanswerable"] else "是"
            lines.extend(
                [
                    f"## {item['question_id']}",
                    "",
                    f"- 问题：{item['question']}",
                    f"- 标准答案：{item['reference_answer']}",
                    f"- 知识库：{item['knowledge_base_name']}",
                    f"- 来源文档：{', '.join(item['document_filenames'])}",
                    f"- Chunk 线索：{', '.join(item['chunk_hints'])}（导入后关联真实 Chunk ID）",
                    f"- 难度：{item['difficulty']}　类型：{item['question_type']}　有答案：{answer_flag}",
                    f"- 标签：{', '.join(item['tags'])}",
                    "- 审核：待人工复核",
                    "",
                    "评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____",
                    "",
                ]
            )
        (_ROOT / filename).write_text("\n".join(lines), encoding="utf-8")
        print(filename, len(rows))


if __name__ == "__main__":
    main()
