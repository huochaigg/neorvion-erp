"""测试必须使用独立库 neorvion_erp_test，避免碰到业务库或其他项目。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

os.environ["APP_ENV"] = "test"
os.environ["MYSQL_DATABASE"] = "neorvion_erp_test"
os.environ["REDIS_DB"] = "15"
os.environ["IAM_REDIS_DB"] = "15"
os.environ["IAM_JWT_ISSUER"] = "neorvion-iam"
os.environ["IAM_JWT_AUDIENCE"] = "neorvion-erp"
os.environ["IAM_JWKS_URL"] = ""
os.environ["IAM_JWT_KEY_ID"] = "jwt-v1"

_JWT_ROOT = Path(tempfile.mkdtemp(prefix="neorvion-erp-jwt-"))
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(_JWT_ROOT / "private.pem").write_bytes(
    _key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
(_JWT_ROOT / "public.pem").write_bytes(
    _key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)
os.environ["IAM_JWT_PRIVATE_KEY_PATH"] = str(_JWT_ROOT / "private.pem")
os.environ["IAM_JWT_PUBLIC_KEY_PATH"] = str(_JWT_ROOT / "public.pem")

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.core.iam import iam_redis_client, jwt_verifier, snapshot_store, test_signer
from app.core.redis import redis_client
from app.db.session import SessionLocal
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from tests.helpers.identity_stub import install_identity_stub, reset_identity_stub

get_settings.cache_clear()
jwt_verifier.cache_clear()
snapshot_store.cache_clear()
test_signer.cache_clear()
install_identity_stub(app)

# 身份中心测试已迁到 services/iam。此处忽略避免双套身份断言。
collect_ignore = [
    "test_auth.py",
    "test_rsa.py",
    "test_tenants.py",
    "test_members.py",
    "test_rbac.py",
    "test_my_permissions.py",
    "test_v235_rbac.py",
]


def _ensure_test_database() -> None:
    settings = get_settings()
    admin_engine = create_engine(settings.build_database_url("mysql"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_test_database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
    admin_engine.dispose()


def _run_migrations() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def setup_test_database() -> Iterator[None]:
    _ensure_test_database()
    _run_migrations()
    yield
    redis_client.flushdb()
    iam_redis_client.flushdb()


def _wipe_business_tables() -> None:
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        session.execute(text("DELETE FROM async_task_logs"))
        session.execute(text("DELETE FROM async_tasks"))
        session.execute(text("DELETE FROM operation_logs"))
        session.execute(text("DELETE FROM system_events"))
        session.execute(text("DELETE FROM inventory_transactions"))
        session.execute(text("DELETE FROM supplier_refund_records"))
        session.execute(text("DELETE FROM purchase_return_outbound_items"))
        session.execute(text("DELETE FROM purchase_return_outbounds"))
        session.execute(text("DELETE FROM purchase_return_items"))
        session.execute(text("DELETE FROM purchase_returns"))
        session.execute(text("DELETE FROM purchase_receipt_items"))
        session.execute(text("DELETE FROM purchase_receipts"))
        session.execute(text("DELETE FROM refund_records"))
        session.execute(text("DELETE FROM return_order_items"))
        session.execute(text("DELETE FROM return_orders"))
        session.execute(text("DELETE FROM after_sale_items"))
        session.execute(text("DELETE FROM after_sale_orders"))
        session.execute(text("DELETE FROM sales_order_items"))
        session.execute(text("DELETE FROM sales_orders"))
        session.execute(text("DELETE FROM customers"))
        session.execute(text("DELETE FROM outbound_pick_lines"))
        session.execute(text("DELETE FROM outbound_picks"))
        session.execute(text("DELETE FROM outbound_order_items"))
        session.execute(text("DELETE FROM outbound_orders"))
        session.execute(text("DELETE FROM shipment_tracking_events"))
        session.execute(text("DELETE FROM shipment_items"))
        session.execute(text("DELETE FROM shipments"))
        session.execute(text("DELETE FROM carriers"))
        session.execute(text("DELETE FROM stocktake_items"))
        session.execute(text("DELETE FROM stocktake_orders"))
        session.execute(text("DELETE FROM stock_transfer_items"))
        session.execute(text("DELETE FROM stock_transfers"))
        session.execute(text("DELETE FROM inventories"))
        session.execute(text("DELETE FROM purchase_order_items"))
        session.execute(text("DELETE FROM purchase_orders"))
        session.execute(text("DELETE FROM suppliers"))
        session.execute(text("DELETE FROM product_skus"))
        session.execute(text("DELETE FROM products"))
        session.execute(text("DELETE FROM brands"))
        session.execute(text("DELETE FROM product_categories"))
        session.execute(text("DELETE FROM warehouses"))
        session.execute(text("DELETE FROM role_permissions"))
        session.execute(text("DELETE FROM member_roles"))
        session.execute(text("DELETE FROM roles"))
        session.execute(text("DELETE FROM tenant_members"))
        session.execute(text("DELETE FROM tenants"))
        session.execute(text("DELETE FROM users"))
        session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    _wipe_business_tables()
    reset_identity_stub()
    yield
    redis_client.flushdb()
    iam_redis_client.flushdb()
    reset_identity_stub()
    _wipe_business_tables()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
