import asyncio

import pytest
from neorvion_db import (
    PRIVILEGED_OPERATION_KEY,
    GlobalIdentityPurpose,
    GlobalIdentitySession,
    PrivilegedOperation,
    PrivilegeError,
    PrivilegeGrant,
    ReviewedSql,
    TenantAsyncSession,
    TenantContextRequired,
    TenantIsolationError,
    TenantRebindError,
    TenantSession,
    open_privileged_async_session,
    open_privileged_session,
    privileged_option,
    require_tenant_id,
    reviewed_sql_option,
)
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session, joinedload, selectinload
from tests.models import Base, Job, Note, Part, Widget
from tests.not_a_worker import steal


def test_plain_session_still_sees_every_tenant(seeded) -> None:
    """生产使用的普通 Session 不被守卫改写。"""
    session = Session(seeded)
    names = set(session.scalars(select(Widget.name)).all())
    session.close()
    assert names == {"alpha", "beta"}


def test_missing_or_invalid_tenant_is_rejected(registry, engine) -> None:
    with pytest.raises(TenantContextRequired):
        TenantSession(0, registry=registry, bind=engine)
    with pytest.raises(TenantContextRequired):
        TenantSession(True, registry=registry, bind=engine)  # type: ignore[arg-type]
    with pytest.raises(TenantIsolationError):
        TenantSession(1, registry=registry, bind=engine, bypass=True)
    plain = Session(engine)
    with pytest.raises(TenantContextRequired):
        require_tenant_id(plain)
    plain.close()


def test_tenant_cannot_be_rebound(registry, engine) -> None:
    session = TenantSession(1, registry=registry, bind=engine)
    session.info["tenant_id"] = 2
    assert session.tenant_id == 1
    with pytest.raises(TenantRebindError):
        session.tenant_id = 2
    with pytest.raises(TenantRebindError):
        session._tenant_id = 2
    session.close()


def test_tenant_a_cannot_read_tenant_b(registry, seeded) -> None:
    session = TenantSession(1, registry=registry, bind=seeded)
    assert require_tenant_id(session) == 1
    assert set(session.scalars(select(Widget.name)).all()) == {"alpha"}
    beta = session.scalar(select(Widget).where(Widget.name == "beta"))
    assert beta is None
    foreign = session.get(Widget, 2)
    assert foreign is None or foreign.tenant_id == 1
    session.close()


def test_join_and_aggregate_stay_inside_tenant(registry, seeded) -> None:
    session = TenantSession(1, registry=registry, bind=seeded)
    total = session.scalar(select(func.count()).select_from(Widget))
    joined = session.execute(
        select(Widget.name, func.count(Part.id))
        .join(Part, Part.widget_id == Widget.id)
        .group_by(Widget.id, Widget.name)
    ).all()
    jobs = session.scalars(select(Job.title)).all()
    session.close()
    assert total == 1
    assert joined == [("alpha", 1)]
    assert list(jobs) == ["tenant-job"]


def test_tenant_object_cannot_reference_other_tenant(registry, seeded) -> None:
    owner = Session(seeded)
    widget_b = owner.scalar(select(Widget).where(Widget.name == "beta"))
    assert widget_b is not None
    widget_b_id = widget_b.id
    owner.expunge(widget_b)
    owner.close()

    session = TenantSession(1, registry=registry, bind=seeded)
    session.add(Part(tenant_id=1, widget_id=widget_b_id))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    attached = Part(tenant_id=1, widget_id=widget_b_id)
    attached.widget = widget_b
    session.add(attached)
    with pytest.raises(TenantIsolationError):
        session.flush()
    session.close()


def test_wrong_tenant_id_is_not_filled_on_flush(registry, engine) -> None:
    session = TenantSession(1, registry=registry, bind=engine)
    session.add(Widget(tenant_id=2, name="stolen"))
    with pytest.raises(TenantIsolationError):
        session.flush()
    session.rollback()
    row = Widget(tenant_id=1, name="kept")
    session.add(row)
    session.flush()
    row.tenant_id = 2
    with pytest.raises(TenantRebindError):
        session.flush()
    session.close()


def test_global_model_remains_readable(registry, seeded) -> None:
    tenant = TenantSession(1, registry=registry, bind=seeded)
    assert tenant.scalar(select(Note.body)) == "shared-note"
    tenant.close()

    identity = GlobalIdentitySession(
        GlobalIdentityPurpose.IAM_DIRECTORY,
        registry=registry,
        bind=seeded,
    )
    assert identity.scalar(select(Note.body)) == "shared-note"
    with pytest.raises(TenantIsolationError):
        identity.execute(select(Widget))
    with pytest.raises(TenantIsolationError):
        identity.execute(select(Job))
    with pytest.raises(TenantContextRequired):
        require_tenant_id(identity)
    identity.close()
    with pytest.raises(TenantIsolationError):
        GlobalIdentitySession("iam_directory", registry=registry, bind=seeded)  # type: ignore[arg-type]


def test_privileged_session_is_not_a_bypass_flag(registry, seeded) -> None:
    with pytest.raises(PrivilegeError):
        PrivilegeGrant(PrivilegedOperation.WORKER_CLAIM, object())
    with pytest.raises(PrivilegeError):
        open_privileged_session(
            "worker_claim",  # type: ignore[arg-type]
            registry=registry,
            allowed_callers=frozenset({__name__}),
            bind=seeded,
        )
    with pytest.raises(PrivilegeError):
        steal(registry, seeded)

    session = open_privileged_session(
        PrivilegedOperation.WORKER_CLAIM,
        registry=registry,
        allowed_callers=frozenset({__name__}),
        bind=seeded,
    )
    with pytest.raises(PrivilegeError):
        session.execute(select(Widget))
    with pytest.raises(PrivilegeError):
        session.execute(
            select(Widget),
            execution_options={PRIVILEGED_OPERATION_KEY: "worker_claim"},
        )
    names = set(
        session.scalars(
            select(Widget.name),
            execution_options=privileged_option(PrivilegedOperation.WORKER_CLAIM),
        ).all()
    )
    session.add(Widget(tenant_id=3, name="claimed"))
    session.commit()
    session.close()
    assert names == {"alpha", "beta"}

    tenant = TenantSession(1, registry=registry, bind=seeded)
    limited = set(
        tenant.scalars(
            select(Widget.name),
            execution_options=privileged_option(PrivilegedOperation.WORKER_CLAIM),
        ).all()
    )
    tenant.close()
    assert limited == {"alpha"}


def test_async_tenant_session_filters_and_rejects_bad_flush(registry) -> None:
    asyncio.run(_async_case(registry))


async def _async_case(registry) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = TenantAsyncSession(1, registry=registry, bind=engine)
    assert isinstance(session.sync_session, TenantSession)
    assert session.tenant_id == 1
    session.add(Widget(tenant_id=1, name="alpha"))
    session.add(Widget(tenant_id=2, name="beta"))
    with pytest.raises(TenantIsolationError):
        await session.flush()
    await session.rollback()
    session.add(Widget(tenant_id=1, name="alpha"))
    await session.commit()
    names = set((await session.scalars(select(Widget.name))).all())
    assert names == {"alpha"}
    privileged = open_privileged_async_session(
        PrivilegedOperation.WORKER_CLAIM,
        registry=registry,
        allowed_callers=frozenset({__name__}),
        bind=engine,
    )
    assert privileged.operation is PrivilegedOperation.WORKER_CLAIM
    await privileged.close()
    await session.close()
    await engine.dispose()


def test_update_requires_matching_tenant_predicate(registry, seeded) -> None:
    """缺少 tenant_id 等值的 ORM UPDATE 拒绝。写对了只改本租户。"""
    missing = TenantSession(1, registry=registry, bind=seeded)
    with pytest.raises(TenantIsolationError):
        missing.execute(update(Widget).where(Widget.name == Widget.name).values(name="renamed"))
    missing.close()

    session = TenantSession(1, registry=registry, bind=seeded)
    with pytest.raises(TenantIsolationError):
        session.execute(update(Widget).where(Widget.tenant_id == 2).values(name="stolen"))
    session.execute(update(Widget).where(Widget.tenant_id == 1).values(name="renamed"))
    session.commit()
    session.close()

    check = Session(seeded)
    rows = dict(check.execute(select(Widget.tenant_id, Widget.name)).all())
    check.close()
    assert rows[1] == "renamed"
    assert rows[2] == "beta"

    blocked = TenantSession(1, registry=registry, bind=seeded)
    with pytest.raises(TenantIsolationError):
        blocked.execute(text("select tenant_id from widgets"))
    with pytest.raises(TenantIsolationError):
        blocked.execute(update(Widget.__table__).values(name="core"))
    blocked.execute(
        update(Widget.__table__).where(Widget.__table__.c.tenant_id == 1).values(name="core-ok")
    )
    with pytest.raises(TenantIsolationError):
        blocked.execute(insert(Widget).values(tenant_id=2, name="insert-b"))
    blocked.execute(insert(Widget).values(tenant_id=1, name="insert-a"))
    with pytest.raises(TenantIsolationError):
        blocked.bulk_insert_mappings(Widget, [{"tenant_id": 1, "name": "bulk"}])
    raw = {row[0] for row in blocked.connection().execute(text("select tenant_id from widgets"))}
    blocked.close()
    assert raw == {1, 2}


def test_join_loaders_subquery_and_refresh_stay_in_tenant(registry, seeded) -> None:
    session = TenantSession(1, registry=registry, bind=seeded)
    loaded = session.scalars(select(Widget).options(selectinload(Widget.parts))).unique().all()
    assert [row.name for row in loaded] == ["alpha"]
    assert [part.tenant_id for part in loaded[0].parts] == [1]

    joined = session.scalars(select(Part).options(joinedload(Part.widget))).unique().one()
    assert joined.widget is not None
    assert joined.widget.name == "alpha"

    scoped = (
        select(func.count()).select_from(Widget).where(Widget.tenant_id == 1).scalar_subquery()
    )
    assert session.scalar(select(scoped)) == 1
    bare = select(func.count()).select_from(Widget).scalar_subquery()
    assert session.scalar(select(bare)) == 1
    joined = (
        select(Part.id, Widget.name)
        .join(Widget, Widget.id == Part.widget_id)
        .where(Part.tenant_id == 1)
    )
    assert session.scalar(select(func.count()).select_from(joined.subquery())) == 1

    row = session.scalar(select(Widget).where(Widget.name == "alpha"))
    assert row is not None
    session.refresh(row)
    assert row.tenant_id == 1
    session.close()


def test_merge_and_autoflush_reject_foreign_tenant(registry, seeded) -> None:
    owner = Session(seeded)
    foreign = owner.scalar(select(Widget).where(Widget.name == "beta"))
    assert foreign is not None
    foreign_id = foreign.id
    owner.close()

    session = TenantSession(1, registry=registry, bind=seeded)
    session.autoflush = True
    session.add(Widget(tenant_id=2, name="late"))
    with pytest.raises(TenantIsolationError):
        session.scalar(select(func.count()).select_from(Widget))
    session.rollback()

    with pytest.raises(TenantIsolationError):
        session.merge(Widget(id=foreign_id, tenant_id=2, name="beta"))
        session.flush()
    session.close()


def test_advisory_lock_text_is_reviewed_and_other_text_is_rejected(registry, engine) -> None:
    session = TenantSession(1, registry=registry, bind=engine)
    with pytest.raises(TenantIsolationError):
        session.execute(
            text("SELECT GET_LOCK(:name, 5)"),
            {"name": "erp:tenant:1"},
        )
    with pytest.raises(TenantIsolationError):
        session.execute(
            text("SELECT GET_LOCK(:name, 5) FROM widgets").execution_options(
                **reviewed_sql_option(ReviewedSql.ADVISORY_LOCK)
            ),
            {"name": "erp:tenant:1"},
        )
    with pytest.raises(Exception) as caught:
        session.execute(
            text("SELECT GET_LOCK(:name, 5)").execution_options(
                **reviewed_sql_option(ReviewedSql.ADVISORY_LOCK)
            ),
            {"name": "erp:tenant:1"},
        )
    assert not isinstance(caught.value, TenantIsolationError)
    session.close()
