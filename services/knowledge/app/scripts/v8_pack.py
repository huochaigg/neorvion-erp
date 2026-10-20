"""写出并校验 V8 题包。

用法：uv run python -m app.scripts.v8_pack

默认只生成 eval_fixtures/v8 下的文档、manifest 和题目，不上传知识库，不写数据库，不调用模型。
"""

from __future__ import annotations

import json

from app.evaluation.v8_catalog import materialize


def main() -> None:
    report = materialize()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
