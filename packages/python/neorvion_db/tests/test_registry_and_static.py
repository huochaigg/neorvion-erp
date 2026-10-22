from pathlib import Path

import pytest
from neorvion_db import AllowedQuery, RegistryError, build_registry, scan_repositories
from tests.models import Base


def test_registry_requires_reason_and_matches_columns() -> None:
    registry = build_registry(Base, {"Note": "全局备注", "Job": "系统任务可空"})
    summary = registry.summary()
    assert summary["tenant_scoped"] == ["parts", "widgets"]
    assert summary["global"] == ["notes"]
    assert summary["nullable_tenant"] == ["jobs"]
    with pytest.raises(RegistryError):
        registry.register(Base, registry.registrations()[0].isolation)
    with pytest.raises(RegistryError):
        build_registry(Base, {"Job": "只有混合表"})


def test_static_check_flags_unregistered_query(tmp_path: Path) -> None:
    repo = tmp_path / "repositories"
    repo.mkdir()
    (repo / "orders.py").write_text(
        "def list_all(session):\n"
        "    return session.execute(select(Order))\n"
        "\n"
        "def list_own(session, tenant_id):\n"
        "    return session.execute(select(Order).where(Order.tenant_id == tenant_id))\n"
        "\n"
        "def load_user(session):\n"
        "    return session.get(User, 1)\n"
        "\n"
        "def get_tenant(session, tenant_id):\n"
        "    return session.get(Tenant, tenant_id)\n"
        "\n"
        "class Repo:\n"
        "    def scoped(self):\n"
        "        return Model.tenant_id == 1\n"
        "\n"
        "    def list_page(self, session):\n"
        "        return session.execute(select(Model).where(self.scoped()))\n",
        encoding="utf-8",
    )
    report = scan_repositories(repo, ())
    assert [item.qualname for item in report.findings] == [
        "orders.py:get_tenant",
        "orders.py:list_all",
        "orders.py:load_user",
    ]
    allowed = (
        AllowedQuery("orders.py:get_tenant", "参数名 tenant_id 不是过滤条件"),
        AllowedQuery("orders.py:list_all", "全局订单目录，测试登记"),
        AllowedQuery("orders.py:load_user", "全局用户主键查找，测试登记"),
    )
    assert scan_repositories(repo, allowed).ok
    with pytest.raises(ValueError):
        scan_repositories(repo, (AllowedQuery("orders.py:list_all", "短"),))
