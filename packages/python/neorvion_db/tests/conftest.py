from collections.abc import Iterator

import pytest
from neorvion_db import IsolationRegistry, build_registry
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.models import Base, Job, Note


@pytest.fixture
def registry() -> IsolationRegistry:
    return build_registry(
        Base,
        {
            "Note": "测试用全局资源，没有 tenant_id",
            "Job": "测试用混合表，空 tenant_id 表示系统任务",
        },
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    bound = create_engine("sqlite://")

    @event.listens_for(bound, "connect")
    def _enable_fk(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bound)
    yield bound
    bound.dispose()


@pytest.fixture
def seeded(engine: Engine) -> Engine:
    """用普通 Session 写入两家企业的数据。这代表当前生产路径，没有自动过滤。"""
    from tests.models import Part, Widget

    session = Session(engine)
    widget_a = Widget(tenant_id=1, name="alpha")
    widget_b = Widget(tenant_id=2, name="beta")
    session.add_all(
        [
            widget_a,
            widget_b,
            Note(body="shared-note"),
            Job(tenant_id=1, title="tenant-job"),
            Job(tenant_id=None, title="system-job"),
        ]
    )
    session.flush()
    session.add_all(
        [
            Part(tenant_id=1, widget_id=widget_a.id),
            Part(tenant_id=2, widget_id=widget_b.id),
        ]
    )
    session.commit()
    session.close()
    return engine
