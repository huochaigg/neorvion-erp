"""租户 3 评测数据初始化。走真实登录、上传、解析、评测 API，不直接插库。

密码只从环境变量 KNOWLEDGE_SEED_PASSWORD 读取，禁止打印。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
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
_PROBE_IDS = ("erp-002", "ecom-008", "adv-006")


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
            timeout=120.0,
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

    def upload(self, knowledge_base_id: int, path: Path) -> None:
        mime = {
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(path.suffix.lower(), "application/octet-stream")
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

    def wait_completed(self, knowledge_base_id: int, timeout: int = 180) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            docs = self.list_documents(knowledge_base_id)
            if docs and all(item.get("status") == "COMPLETED" for item in docs):
                return
            failed = [item["filename"] for item in docs if item.get("status") == "FAILED"]
            if failed:
                raise RuntimeError(f"文档处理失败: {failed}")
            time.sleep(2)
        raise RuntimeError("等待解析/切片/向量超时，请检查模型 API Key 与 Worker")

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

    def probe(self, case_id: int, *, generate: bool) -> dict:
        return self._data(
            self.client.post(
                f"/api/v1/evaluation/cases/{case_id}/probe",
                json={"strategy": "HYBRID", "top_k": 8, "rerank": True, "generate": generate},
            )
        )


def _ensure_bases(api: KnowledgeClient) -> dict[str, int]:
    existed = {item["name"]: item["id"] for item in api.list_bases()}
    mapping: dict[str, int] = {}
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
        current = {item["filename"] for item in api.list_documents(mapping[name])}
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in {".md", ".txt", ".pdf", ".docx"}:
                continue
            if path.name in current:
                print(f"跳过已存在文档 {path.name}")
                continue
            api.upload(mapping[name], path)
            print(f"上传 {path.name}")
        api.wait_completed(mapping[name])
        status = api.index_status(mapping[name])
        print(
            f"索引 {name}: chunks={status.get('total_active_chunks')} "
            f"ready={status.get('ready')} pending={status.get('pending')} "
            f"failed={status.get('failed')}"
        )
        if not status.get("ready"):
            print(f"警告：{name} 尚无 READY 向量，VECTOR 检索不可用。请配置 EMBEDDING_API_KEY 后重建索引。")
    return mapping


def _label_chunks(api: KnowledgeClient, kb_id: int, hints: list[str], filenames: list[str]) -> list[dict]:
    seen: set[int] = set()
    judgments: list[dict] = []
    queries = list(hints) or filenames
    for query in queries[:4]:
        hits = api.search(query, kb_id)
        for hit in hits:
            if filenames and hit.get("filename") not in filenames:
                continue
            chunk_id = int(hit["chunk_id"])
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            judgments.append({"chunk_id": chunk_id, "relevance": 3 if len(judgments) == 0 else 2})
            if len(judgments) >= 3:
                return judgments
    return judgments


def _write_probe_report(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# V5 抽样评测结果", "", "以下来自本地真实 probe 接口，不是硬编码指标。", ""]
    for row in rows:
        lines.append(f"## {row.get('question_id')} / case {row.get('case_id')}")
        lines.append("")
        lines.append(f"- 问题：{row.get('question')}")
        lines.append(f"- 策略：{row.get('strategy')}  rerank_applied={row.get('rerank_applied')} degraded={row.get('rerank_degraded')}")
        lines.append(f"- 耗时：{row.get('latency_ms')} ms")
        lines.append(f"- stages：`{json.dumps(row.get('stages'), ensure_ascii=False)}`")
        lines.append(f"- retrieval_metrics：`{json.dumps(row.get('retrieval_metrics'), ensure_ascii=False)}`")
        lines.append(f"- usage：`{json.dumps(row.get('usage'), ensure_ascii=False)}`")
        if row.get("answer"):
            lines.append(f"- 模型回答：{row['answer']}")
        lines.append("")
        lines.append("召回 Chunk：")
        for item in row.get("retrieved") or []:
            lines.append(f"- #{item.get('final_rank')} chunk={item.get('chunk_id')} {item.get('filename')} vec={item.get('vector_score')} kw={item.get('keyword_score')}")
        lines.append("")
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
        bases = _ensure_bases(api)
        dataset_name = "V5-RAG-100"
        existed = next((item for item in api.list_datasets() if item["name"] == dataset_name), None)
        dataset = existed or api.create_dataset(dataset_name, list(bases.values()))
        questions = all_questions()
        if len(questions) != 100:
            raise RuntimeError(f"题目数量应为 100，实际 {len(questions)}")
        payload = []
        pending_review = 0
        for item in questions:
            kb_id = bases[item["knowledge_base_name"]]
            judgments = []
            if not item["is_unanswerable"]:
                judgments = _label_chunks(api, kb_id, item["chunk_hints"], item["document_filenames"])
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
        for qid in _PROBE_IDS:
            row = cases.get(qid)
            if not row:
                print(f"未找到抽样题 {qid}，跳过")
                continue
            probed = api.probe(int(row["id"]), generate=generate)
            probed["question_id"] = qid
            reports.append(probed)
            print(f"probe {qid} latency={probed.get('latency_ms')} metrics={probed.get('retrieval_metrics')}")
        report_path = Path(__file__).resolve().parents[4] / "docs" / "knowledge" / "evaluation" / "sample-results.md"
        if reports:
            _write_probe_report(reports, report_path)
            print(f"抽样报告: {report_path}")
        if args.probe_only:
            return 0
        print("初始化完成。请在前端 /datasets 查看 V5-RAG-100，剩余题目不要批量跑真实模型。")
        return 0
    finally:
        api.close()


if __name__ == "__main__":
    raise SystemExit(main())
