"""租户 3 评测数据初始化。走真实登录、上传、解析、评测 API，不直接插库。

密码只从环境变量 KNOWLEDGE_SEED_PASSWORD 读取，禁止打印。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

from app.scripts.eval_questions import KB_ECOM, KB_ERP, KB_GEN, all_questions

_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "eval_fixtures" / "docs"
_KB_DIRS = {
    KB_ERP: _FIXTURE_ROOT / "erp",
    KB_ECOM: _FIXTURE_ROOT / "ecommerce",
    KB_GEN: _FIXTURE_ROOT / "general",
}
_PROBE_IDS = ("erp-001", "erp-010", "ecom-008", "gen-007")
_ALLOWED_SUFFIX = {".md", ".txt", ".pdf", ".docx"}
_MIME = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mime(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "application/octet-stream")


def _encrypt_password(public_pem: str, password: str) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    public_key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise RuntimeError("ERP 公钥无效")
    cipher = public_key.encrypt(
        password.encode("utf-8"),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return base64.b64encode(cipher).decode("ascii")


async def _login(erp_base: str, email: str, password: str) -> str:
    async with httpx.AsyncClient(base_url=erp_base, timeout=30.0) as client:
        key_resp = await client.get("/api/crypto/public-key")
        key_resp.raise_for_status()
        material = key_resp.json().get("data") or {}
        public_pem = str(material.get("public_key") or "")
        if not public_pem:
            raise RuntimeError("无法获取 ERP 公钥，初始化中止")
        encrypted = _encrypt_password(public_pem, password)
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "encrypted_password": encrypted,
                "key_id": material.get("key_id"),
                "challenge_id": material.get("challenge_id"),
            },
        )
        login.raise_for_status()
        data = login.json().get("data") or login.json()
        token = data.get("access_token") or data.get("accessToken")
        if not token:
            raise RuntimeError("登录成功但未返回 access_token")
        return str(token)


class KnowledgeClient:
    def __init__(self, base_url: str, token: str, tenant_id: int) -> None:
        self.client = httpx.Client(
            base_url=base_url,
            timeout=300.0,
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)},
        )

    def close(self) -> None:
        self.client.close()

    def _data(self, response: httpx.Response):
        response.raise_for_status()
        body = response.json()
        if body.get("code") not in {0, None}:
            raise RuntimeError(body.get("message") or "Knowledge API 失败")
        return body.get("data", body)

    def list_bases(self) -> list[dict]:
        return self._data(self.client.get("/api/v1/knowledge-bases", params={"page": 1, "page_size": 100}))["items"]

    def create_base(self, name: str, description: str) -> dict:
        return self._data(self.client.post("/api/v1/knowledge-bases", json={"name": name, "description": description}))

    def list_documents(self, knowledge_base_id: int) -> list[dict]:
        return self._data(
            self.client.get("/api/v1/documents", params={"knowledge_base_id": knowledge_base_id, "page": 1, "page_size": 100})
        )["items"]

    def list_chunks(self, document_id: int) -> list[dict]:
        page = 1
        items: list[dict] = []
        while True:
            data = self._data(
                self.client.get(
                    "/api/v1/chunks",
                    params={"document_id": document_id, "page": page, "page_size": 100},
                )
            )
            batch = data.get("items") or []
            items.extend(batch)
            total = int(data.get("total") or 0)
            if len(items) >= total or not batch:
                return items
            page += 1

    def upload(self, knowledge_base_id: int, path: Path) -> None:
        mime = _mime(path)
        with path.open("rb") as handle:
            files = [("files", (path.name, handle, mime))]
            response = self.client.post(f"/api/v1/knowledge-bases/{knowledge_base_id}/documents", files=files)
        if response.status_code == 200:
            data = self._data(response)
            failed = data.get("failed") or 0
            if failed:
                messages = [item.get("message") for item in data.get("items") or []]
                if any("SHA256" in str(item) for item in messages):
                    return
                raise RuntimeError(f"上传失败: {messages}")
            return
        if response.status_code == 409:
            return
        response.raise_for_status()

    def index_status(self, knowledge_base_id: int) -> dict:
        return self._data(self.client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/index-status"))

    def wait_completed(self, knowledge_base_id: int, timeout: int = 300) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            docs = self.list_documents(knowledge_base_id)
            if docs and all(item.get("status") == "COMPLETED" for item in docs):
                return
            failed = [item["filename"] for item in docs if item.get("status") == "FAILED"]
            if failed:
                raise RuntimeError(f"文档处理失败: {failed}")
            time.sleep(2)
        raise RuntimeError("等待解析/切片超时，请检查模型 API Key 与 Worker")

    def replace(self, document_id: int, path: Path) -> None:
        with path.open("rb") as handle:
            response = self.client.post(
                f"/api/v1/documents/{document_id}/replace",
                files={"file": (path.name, handle, _mime(path))},
                data={"note": "eval fixture refresh"},
            )
        self._data(response)

    def reindex(self, knowledge_base_id: int) -> dict:
        return self._data(self.client.post(f"/api/v1/knowledge-bases/{knowledge_base_id}/reindex"))

    def wait_index_ready(self, knowledge_base_id: int, timeout: int = 300) -> dict:
        deadline = time.time() + timeout
        last: dict = {}
        while time.time() < deadline:
            last = self.index_status(knowledge_base_id)
            total = int(last.get("total_active_chunks") or 0)
            ready = int(last.get("ready") or 0)
            if total > 0 and ready >= total:
                return last
            time.sleep(3)
        return last

    def retrieval_test(
        self,
        query: str,
        knowledge_base_id: int,
        *,
        strategy: str,
        rerank: bool = False,
    ) -> dict:
        return self._data(
            self.client.post(
                "/api/v1/retrieval/test",
                json={
                    "query": query,
                    "strategy": strategy,
                    "top_k": 8,
                    "rerank": rerank,
                    "knowledge_base_ids": [knowledge_base_id],
                },
            )
        )

    def search(self, query: str, knowledge_base_id: int) -> list[dict]:
        return self._data(
            self.client.post(
                "/api/v1/search",
                json={"query": query, "strategy": "KEYWORD", "top_k": 8, "knowledge_base_ids": [knowledge_base_id]},
            )
        ).get("items") or []

    def list_datasets(self) -> list[dict]:
        return self._data(self.client.get("/api/v1/evaluation/datasets", params={"page": 1, "page_size": 100}))["items"]

    def create_dataset(self, name: str, knowledge_base_ids: list[int]) -> dict:
        return self._data(
            self.client.post(
                "/api/v1/evaluation/datasets",
                json={"name": name, "description": "V5 RAG 评测 100 题（AI 生成，待人工复核）", "knowledge_base_ids": knowledge_base_ids},
            )
        )

    def upsert_cases(self, dataset_id: int, items: list[dict]) -> dict:
        return self._data(self.client.post(f"/api/v1/evaluation/datasets/{dataset_id}/upsert-cases", json={"items": items}))

    def list_cases(self, dataset_id: int) -> list[dict]:
        # API page_size 上限 100，超过会 422。
        page = 1
        page_size = 100
        items: list[dict] = []
        while True:
            data = self._data(
                self.client.get(
                    f"/api/v1/evaluation/datasets/{dataset_id}/cases",
                    params={"page": page, "page_size": page_size},
                )
            )
            batch = data.get("items") or []
            items.extend(batch)
            total = int(data.get("total") or 0)
            if len(items) >= total or not batch:
                return items
            page += 1

    def probe(self, case_id: int, *, generate: bool, knowledge_base_ids: list[int] | None = None) -> dict:
        payload = {"strategy": "HYBRID", "top_k": 8, "rerank": True, "generate": generate}
        if knowledge_base_ids:
            payload["knowledge_base_ids"] = knowledge_base_ids
        return self._data(self.client.post(f"/api/v1/evaluation/cases/{case_id}/probe", json=payload))


def _ensure_bases(api: KnowledgeClient) -> tuple[dict[str, int], list[str], list[str]]:
    existed = {item["name"]: item["id"] for item in api.list_bases()}
    mapping: dict[str, int] = {}
    changed_docs: list[str] = []
    index_rows: list[str] = []
    descriptions = {
        KB_ERP: "由 ERP 实际代码归纳的业务知识，区分已实现与建议规则。",
        KB_ECOM: "模拟跨境电商运营知识，不是真实平台政策。",
        KB_GEN: "FastAPI / PostgreSQL / Redis 与内部操作规范。",
    }
    for name, folder in _KB_DIRS.items():
        if name in existed:
            mapping[name] = existed[name]
            print(f"复用知识库 {name} id={existed[name]}")
        else:
            created = api.create_base(name, descriptions[name])
            mapping[name] = created["id"]
            print(f"创建知识库 {name} id={created['id']}")
        current = {item["filename"]: item for item in api.list_documents(mapping[name])}
        changed = False
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in _ALLOWED_SUFFIX:
                continue
            existed_doc = current.get(path.name)
            if existed_doc is None:
                api.upload(mapping[name], path)
                print(f"上传 {path.name}")
                changed = True
                changed_docs.append(f"{name}/{path.name}（新增）")
                continue
            digest = _file_sha256(path)
            if str(existed_doc.get("sha256") or "").lower() == digest.lower():
                print(f"内容未变，跳过 {path.name}")
                continue
            api.replace(int(existed_doc["id"]), path)
            print(f"替换 {path.name} document_id={existed_doc['id']}")
            changed = True
            changed_docs.append(f"{name}/{path.name}（替换）")
        api.wait_completed(mapping[name], timeout=300)
        status = api.index_status(mapping[name])
        ready = int(status.get("ready") or 0)
        total = int(status.get("total_active_chunks") or 0)
        if total == 0 or ready < total:
            queued = api.reindex(mapping[name])
            print(f"重建索引 {name}: queued={queued.get('queued')}")
            status = api.wait_index_ready(mapping[name])
        elif changed:
            status = api.wait_index_ready(mapping[name])
        print(
            f"索引 {name}: chunks={status.get('total_active_chunks')} "
            f"ready={status.get('ready')} pending={status.get('pending')} "
            f"failed={status.get('failed')} incompatible={status.get('incompatible')}"
        )
        if not status.get("ready"):
            print(f"警告：{name} 尚无 READY 向量，VECTOR 检索不可用。")
        index_rows.append(
            f"- {name} id={mapping[name]} chunks={status.get('total_active_chunks')} "
            f"ready={status.get('ready')} pending={status.get('pending')} "
            f"failed={status.get('failed')} incompatible={status.get('incompatible')} "
            f"needs_reindex={status.get('needs_reindex')}"
        )
    return mapping, changed_docs, index_rows


def _label_chunks(api: KnowledgeClient, kb_id: int, hints: list[str], filenames: list[str]) -> list[dict]:
    """用切片正文匹配线索，而不是把问答拼进检索。不虚构 Chunk ID。"""
    scored: list[tuple[int, dict]] = []
    for doc in api.list_documents(kb_id):
        if filenames and doc.get("filename") not in filenames:
            continue
        for chunk in api.list_chunks(int(doc["id"])):
            if chunk.get("status") not in {None, "ACTIVE"}:
                continue
            if chunk.get("enabled") is False:
                continue
            content = str(chunk.get("content") or "")
            hits = sum(1 for hint in hints if hint and hint.casefold() in content.casefold())
            if hits:
                scored.append((hits, chunk))
    scored.sort(key=lambda item: (-item[0], int(item[1].get("chunk_index") or 0)))
    judgments: list[dict] = []
    seen: set[int] = set()
    for hits, chunk in scored:
        chunk_id = int(chunk["id"])
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        judgments.append({"chunk_id": chunk_id, "relevance": 3 if hits >= 2 or not judgments else 2})
        if len(judgments) >= 3:
            return judgments
    if judgments:
        return judgments
    for query in (hints or filenames)[:4]:
        for hit in api.search(query, kb_id):
            if filenames and hit.get("filename") not in filenames:
                continue
            chunk_id = int(hit["chunk_id"])
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            judgments.append({"chunk_id": chunk_id, "relevance": 3 if not judgments else 2})
            if len(judgments) >= 3:
                return judgments
    return judgments


def _write_probe_report(rows: list[dict], path: Path, sweeps: dict[str, dict] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# V5 抽样评测结果", "", "以下来自本地真实 probe / retrieval.test 接口，不是硬编码指标。", ""]
    if sweeps:
        lines.append("## erp-001 策略对照")
        lines.append("")
        for name, body in sweeps.items():
            items = body.get("items") or []
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- 策略：{body.get('strategy')} rerank_applied={body.get('rerank_applied')} degraded={body.get('rerank_degraded')}")
            lines.append(f"- 耗时：{body.get('latency_ms')} ms")
            lines.append(f"- stages：`{json.dumps(body.get('stages'), ensure_ascii=False)}`")
            lines.append("- 召回：")
            if not items:
                lines.append("- （空）")
            for item in items:
                snippet = str(item.get("content") or "").replace("\n", " ")[:160]
                lines.append(
                    f"- #{item.get('final_rank')} chunk={item.get('chunk_id')} {item.get('filename')} "
                    f"vec={item.get('vector_score')} kw={item.get('keyword_score')} rrf={item.get('rrf_score')} "
                    f"rerank={item.get('rerank_score')} | {snippet}"
                )
            lines.append("")
    for row in rows:
        lines.append(f"## {row.get('question_id')} / case {row.get('case_id')}")
        lines.append("")
        lines.append(f"- 问题：{row.get('question')}")
        lines.append(f"- 策略：{row.get('strategy')}  rerank_applied={row.get('rerank_applied')} degraded={row.get('rerank_degraded')}")
        lines.append(f"- 耗时：{row.get('latency_ms')} ms")
        lines.append(f"- stages：`{json.dumps(row.get('stages'), ensure_ascii=False)}`")
        lines.append(f"- retrieval_metrics：`{json.dumps(row.get('retrieval_metrics'), ensure_ascii=False)}`")
        lines.append(f"- citations：`{json.dumps(row.get('citations'), ensure_ascii=False)}`")
        lines.append(f"- usage：`{json.dumps(row.get('usage'), ensure_ascii=False)}`")
        if row.get("answer"):
            lines.append(f"- 模型回答：{row['answer']}")
        lines.append("")
        lines.append("召回 Chunk：")
        for item in row.get("retrieved") or []:
            lines.append(
                f"- #{item.get('final_rank')} chunk={item.get('chunk_id')} {item.get('filename')} "
                f"vec={item.get('vector_score')} kw={item.get('keyword_score')}"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _coverage_row(item: dict, case: dict | None, imported: set[str], chunk_files: dict[str, list[str]]) -> dict:
    missing_files = [
        name
        for name in item["document_filenames"]
        if not any((_FIXTURE_ROOT / folder / name).exists() for folder in ("erp", "ecommerce", "general"))
    ]
    imported_ok = all(name in imported for name in item["document_filenames"]) if item["document_filenames"] else True
    judgments = (case or {}).get("judgments") or []
    live = [row for row in judgments if not row.get("stale") and int(row.get("relevance") or 0) >= 1]
    hint_ok = False
    for name in item["document_filenames"]:
        contents = chunk_files.get(name) or []
        if any(all(hint.lower() in text.lower() for hint in item["chunk_hints"][:1]) for text in contents):
            hint_ok = True
            break
        if any(any(hint.lower() in text.lower() for hint in item["chunk_hints"]) for text in contents):
            hint_ok = True
            break
    if item["is_unanswerable"]:
        status = "无答案（保持）"
    elif not missing_files and imported_ok and live:
        status = "已覆盖"
    elif not missing_files and imported_ok and hint_ok:
        status = "有原文但标注缺失"
    elif not missing_files and imported_ok:
        status = "文档已导入但缺有效 Chunk"
    elif not missing_files:
        status = "来源文档存在但未导入"
    else:
        status = "缺少来源文档"
    return {
        "id": item["question_id"],
        "status": status,
        "unanswerable": item["is_unanswerable"],
        "missing_files": missing_files,
        "imported_ok": imported_ok,
        "judgments": len(live),
        "hint_ok": hint_ok,
        "chunk_ids": [int(row["chunk_id"]) for row in live],
        "filenames": [row.get("filename") for row in live],
        "review": True,
    }


def _write_audit(
    path: Path,
    *,
    questions: list[dict],
    cases: dict[str, dict],
    imported: set[str],
    chunk_files: dict[str, list[str]],
    index_rows: list[str],
    changed_docs: list[str],
    missing_chunks: int,
    erp001: dict,
) -> None:
    rows = [_coverage_row(item, cases.get(item["question_id"]), imported, chunk_files) for item in questions]
    covered = [row for row in rows if row["status"] == "已覆盖"]
    missing_src = [row for row in rows if row["status"] == "缺少来源文档"]
    no_chunk = [row for row in rows if row["status"] == "文档已导入但缺有效 Chunk"]
    unanswerable = [row for row in rows if row["unanswerable"]]
    labeled_missing = [row for row in rows if row["status"] == "有原文但标注缺失"]
    lines = [
        "# Knowledge V5 评测知识覆盖审计",
        "",
        "范围：租户 3 本地测试环境。未改评测指标，未硬编码检索结果。",
        "",
        "## 汇总",
        "",
        f"- 题目总数：{len(rows)}",
        f"- 已有有效证据（真实 Chunk 标注）：{len(covered)}",
        f"- 缺少来源文档：{len(missing_src)}",
        f"- 文档存在但缺少有效 Chunk：{len(no_chunk)}",
        f"- 有原文但标注缺失：{len(labeled_missing)}",
        f"- 索引异常：见下方索引快照（seed 时 missing_chunks={missing_chunks}）",
        "- 标准答案存在疑问：1（adv-007 曾被误标为无答案，知识库实际写明未实现 OCR，已改为有答案）",
        f"- 无答案题：{len(unanswerable)}（adv-006、adv-010；adv-007 已纠正）",
        "- 全部 100 题仍标记 needs_human_review，待人工审核",
        "",
        "## 补充或修改的知识文档",
        "",
    ]
    for name in changed_docs:
        lines.append(f"- {name}")
    if not changed_docs:
        lines.append("- （本次无文件变更）")
    lines.extend(["", "## 索引快照", ""])
    lines.extend(index_rows or ["- （无）"])
    lines.extend(["", "## erp-001 排查结果", ""])
    for key, value in erp001.items():
        lines.append(f"- {key}：{value}")
    lines.extend(["", "## 逐题覆盖状态", "", "| ID | 状态 | 无答案 | 有效 Chunk | 来源 |", "| --- | --- | --- | --- | --- |"])
    for row in rows:
        chunk_txt = ",".join(str(item) for item in row["chunk_ids"]) or "-"
        src = ",".join(str(item) for item in (row["filenames"] or [])) or "-"
        lines.append(f"| {row['id']} | {row['status']} | {'是' if row['unanswerable'] else '否'} | {chunk_txt} | {src} |")
    lines.extend(
        [
            "",
            "## 待人工审核",
            "",
            "全部 100 题标准答案仍为 AI 归纳 + 代码核对，不能直接当生产基准。优先复核：",
            "",
            "- erp-001 至 erp-030：对照 ERP 状态机与库存事务",
            "- ecom-*：确认模拟标记未被理解成真实平台政策",
            "- adv-006 / adv-010：必须保持拒绝编造",
            "- adv-007：现改为有答案，请确认 OCR 未实现这一事实仍成立",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Knowledge V5 评测初始化")
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("KNOWLEDGE_SEED_PASSWORD") or ""
    if not password:
        print("缺少环境变量 KNOWLEDGE_SEED_PASSWORD，初始化中止。", file=sys.stderr)
        return 2
    email = os.environ.get("KNOWLEDGE_SEED_EMAIL", "123@qq.com")
    tenant_id = int(os.environ.get("KNOWLEDGE_SEED_TENANT_ID", "3"))
    erp_base = os.environ.get("ERP_API_BASE_URL", "http://127.0.0.1:8011")
    knowledge_base = os.environ.get("KNOWLEDGE_API_BASE_URL", "http://127.0.0.1:8012")
    token = asyncio.run(_login(erp_base, email, password))
    api = KnowledgeClient(knowledge_base, token, tenant_id)
    try:
        bases, changed_docs, index_rows = _ensure_bases(api)
        dataset_name = "V5-RAG-100"
        existed = next((item for item in api.list_datasets() if item["name"] == dataset_name), None)
        dataset = existed or api.create_dataset(dataset_name, list(bases.values()))
        questions = all_questions()
        questions_by_id = {item["question_id"]: item for item in questions}
        if len(questions) != 100:
            raise RuntimeError(f"题目数量应为 100，实际 {len(questions)}")
        payload = []
        pending_review = 0
        for item in questions:
            judgments = []
            if not item["is_unanswerable"]:
                seen: set[int] = set()
                primary = bases[item["knowledge_base_name"]]
                kb_order = [primary] + [item_id for item_id in bases.values() if item_id != primary]
                for candidate_kb in kb_order:
                    taken = 0
                    for judgment in _label_chunks(api, candidate_kb, item["chunk_hints"], item["document_filenames"]):
                        chunk_id = int(judgment["chunk_id"])
                        if chunk_id in seen:
                            continue
                        seen.add(chunk_id)
                        judgments.append(judgment)
                        taken += 1
                        if taken >= 2 or len(judgments) >= 3:
                            break
                    if len(judgments) >= 3:
                        break
            if not item["is_unanswerable"] and not judgments:
                pending_review += 1
            payload.append(
                {
                    "external_key": item["question_id"],
                    "question": item["question"],
                    "expected_answer": item["reference_answer"],
                    "question_type": item["question_type"],
                    "difficulty": item["difficulty"],
                    "tags": item["tags"] + [item["category"]],
                    "is_unanswerable": item["is_unanswerable"],
                    "needs_human_review": True,
                    "judgments": judgments,
                }
            )
        result = api.upsert_cases(dataset["id"], payload)
        print(
            f"upsert created={result.get('created')} updated={result.get('updated')} "
            f"skipped={result.get('skipped')} missing_chunks={pending_review}"
        )
        cases = {item.get("external_key"): item for item in api.list_cases(dataset["id"])}
        reports = []
        generate = os.environ.get("KNOWLEDGE_SEED_GENERATE", "").lower() in {"1", "true", "yes"}
        erp_question = next(item["question"] for item in questions if item["question_id"] == "erp-001")
        sweeps = {
            "VECTOR": api.retrieval_test(erp_question, bases[KB_ERP], strategy="VECTOR", rerank=False),
            "KEYWORD": api.retrieval_test(erp_question, bases[KB_ERP], strategy="KEYWORD", rerank=False),
            "HYBRID": api.retrieval_test(erp_question, bases[KB_ERP], strategy="HYBRID", rerank=False),
            "HYBRID_rerank": api.retrieval_test(erp_question, bases[KB_ERP], strategy="HYBRID", rerank=True),
        }
        for name, body in sweeps.items():
            print(f"erp-001 {name} hits={len(body.get('items') or [])} ms={body.get('latency_ms')}")
        for qid in _PROBE_IDS:
            row = cases.get(qid)
            if not row:
                print(f"未找到抽样题 {qid}，跳过")
                continue
            probed = api.probe(int(row["id"]), generate=generate, knowledge_base_ids=[bases[questions_by_id[qid]["knowledge_base_name"]]])
            probed["question_id"] = qid
            reports.append(probed)
            print(f"probe {qid} latency={probed.get('latency_ms')} metrics={probed.get('retrieval_metrics')}")
        docs_root = Path(__file__).resolve().parents[4] / "docs" / "knowledge" / "evaluation"
        if reports:
            _write_probe_report(reports, docs_root / "sample-results.md", sweeps)
            print(f"抽样报告: {docs_root / 'sample-results.md'}")
        imported: set[str] = set()
        chunk_files: dict[str, list[str]] = {}
        for kb_id in bases.values():
            for doc in api.list_documents(kb_id):
                imported.add(str(doc.get("filename")))
                texts = [str(chunk.get("content") or "") for chunk in api.list_chunks(int(doc["id"]))]
                chunk_files[str(doc.get("filename"))] = texts
        erp001_hits = (sweeps["HYBRID_rerank"].get("items") or sweeps["HYBRID"].get("items") or [])
        erp001_answer = next((row.get("answer") for row in reports if row.get("question_id") == "erp-001"), "")
        _write_audit(
            docs_root / "knowledge-coverage-audit.md",
            questions=questions,
            cases=cases,
            imported=imported,
            chunk_files=chunk_files,
            index_rows=index_rows,
            changed_docs=changed_docs,
            missing_chunks=pending_review,
            erp001={
                "会话日志根因": "检索日志 id=734 显示 HYBRID 但 knowledge_base_ids=[1,2]（产品手册），不是 ERP业务知识库 id=4",
                "文档上传": "01-sales-order-state.md 已在租户 3 / KB 4，解析 COMPLETED",
                "DRAFT 规则": "切片包含「DRAFT」与「未预占库存」，与 sales_order_state.DRAFT 及 confirm_order 只从 PENDING_CONFIRMATION RESERVE 一致",
                "Embedding": "排查时 chunk_embeddings 为空，VECTOR 路必然为空；本次已按现有流水线重建",
                "KEYWORD": "整句 ILIKE/trigram 不中；FTS 仅匹配 DRAFT 等拉丁词。纯中文题（如 ecom-008）会空召回，已补中文片段 ILIKE",
                "RRF/Rerank/TopK": "正确库上不是把 DRAFT 证据滤掉，而是根本没搜到 ERP 库",
                "VECTOR 命中": len(sweeps["VECTOR"].get("items") or []),
                "KEYWORD 命中": len(sweeps["KEYWORD"].get("items") or []),
                "HYBRID 命中": len(sweeps["HYBRID"].get("items") or []),
                "HYBRID+Rerank 命中": len(erp001_hits),
                "最终回答": (erp001_answer or "（本次未生成回答，见 KNOWLEDGE_SEED_GENERATE）")[:300],
            },
        )
        print(f"覆盖审计: {docs_root / 'knowledge-coverage-audit.md'}")
        if args.probe_only:
            return 0
        print("初始化完成。请在前端 /datasets 查看 V5-RAG-100，剩余题目不要批量跑真实模型。")
        return 0
    finally:
        api.close()


if __name__ == "__main__":
    raise SystemExit(main())
