import pytest
from app.core.config import Settings
from pydantic import ValidationError
from sqlalchemy.engine import make_url


def test_copilot_database_is_independent(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://neorvion_copilot:test-only@127.0.0.1:5432/neorvion_copilot_test",
    )
    url = make_url(Settings(_env_file=None).database_url)  # type: ignore[call-arg]
    assert url.database == "neorvion_copilot_test"
    assert url.username == "neorvion_copilot"
    assert url.database != "neorvion_knowledge"


def test_database_url_has_no_hard_coded_fallback(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
