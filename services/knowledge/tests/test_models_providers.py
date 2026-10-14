from __future__ import annotations

from app.ai.dashscope import DashScopeRerankClient, dashscope_rerank_url
from app.ai.factory import get_chat_client, get_embedding_client, get_rerank_client
from app.ai.mock import MockChatClient, MockEmbeddingClient, MockRerankClient
from app.ai.openai_compat import _classify_http_error
from app.core.config import Settings
from app.core.exceptions import AppError
from fastapi.testclient import TestClient

from tests.conftest import ALL_KNOWLEDGE_PERMS, FakeIdentityClient, auth_header


def test_default_models_are_not_openai_official() -> None:
    assert Settings.model_fields["chat_model"].default == "deepseek-flash"
    assert Settings.model_fields["chat_model"].default != "gpt-4o-mini"
    assert Settings.model_fields["embedding_model"].default == "text-embedding-v4"
    assert Settings.model_fields["embedding_dimensions"].default == 1024
    assert Settings.model_fields["rerank_model"].default == "qwen3-rerank"
    assert Settings.model_fields["rerank_provider"].default == "dashscope"
    assert Settings.model_fields["chat_base_url"].default == "https://api.deepseek.com"


def test_key_fallbacks() -> None:
    settings = Settings.model_construct(
        chat_api_key="",
        deepseek_api_key="ds-key",
        embedding_api_key="",
        dashscope_api_key="ds-scope",
        rerank_api_key="",
    )
    assert settings.resolved_chat_api_key() == "ds-key"
    assert settings.resolved_embedding_api_key() == "ds-scope"
    assert settings.resolved_rerank_api_key() == "ds-scope"
    assert settings.chat_api_key_env() == "DEEPSEEK_API_KEY"
    assert settings.embedding_api_key_env() == "DASHSCOPE_API_KEY"
    assert settings.rerank_api_key_env() == "DASHSCOPE_API_KEY"


def test_dashscope_rerank_url_from_workspace_embedding() -> None:
    url = dashscope_rerank_url("https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    assert url == "https://ws-demo.cn-beijing.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    assert "/chat/completions" not in url
    client = DashScopeRerankClient(
        base_url="https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        api_key="x",
        model="qwen3-rerank",
    )
    assert client.url == url


def test_dashscope_rerank_url_refuses_unknown_host() -> None:
    try:
        dashscope_rerank_url("https://api.openai.com/v1")
    except AppError as exc:
        assert exc.code == 50364
    else:
        raise AssertionError("should reject unrelated host")


def test_model_error_classification_details() -> None:
    assert _classify_http_error(401, '{"code":"InvalidApiKey"}').code == 40160
    assert _classify_http_error(402, '{"message":"Arrearage"}').code == 40260
    assert _classify_http_error(404, "nope").code == 40461
    missing = _classify_http_error(400, '{"error":{"message":"The model does not exist","type":"invalid_request_error"}}')
    assert missing.code == 40460
    assert "sk-secret" not in _classify_http_error(400, "bad sk-secret-value").message


def test_mock_factory_still_used_in_tests() -> None:
    get_embedding_client.cache_clear()
    get_chat_client.cache_clear()
    get_rerank_client.cache_clear()
    assert isinstance(get_embedding_client(), MockEmbeddingClient)
    assert isinstance(get_chat_client(), MockChatClient)
    assert isinstance(get_rerank_client(), MockRerankClient)


def test_models_page_and_connectivity(client: TestClient, identity: FakeIdentityClient) -> None:
    identity.grant(1, 11, permissions=ALL_KNOWLEDGE_PERMS)
    headers = auth_header(1, 11)
    listed = client.get("/api/v1/models", headers=headers)
    assert listed.status_code == 200, listed.text
    kinds = {item["kind"]: item for item in listed.json()["data"]}
    assert kinds["CHAT"]["model_name"] == "mock-chat"
    assert kinds["EMBEDDING"]["dimensions"] == 8
    chat = client.post("/api/v1/models/test", json={"kind": "CHAT"}, headers=headers)
    assert chat.status_code == 200, chat.text
    assert chat.json()["data"]["last_test_ok"] is True
    embed = client.post("/api/v1/models/test", json={"kind": "EMBEDDING"}, headers=headers)
    assert embed.status_code == 200, embed.text
    assert "维" in (embed.json()["data"]["last_test_message"] or "")
    rerank = client.post("/api/v1/models/test", json={"kind": "RERANK"}, headers=headers)
    assert rerank.status_code == 200, rerank.text
