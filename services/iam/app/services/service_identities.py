from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.jwt_keys import get_jwt_signer
from app.core.permissions import PERMISSION_CATALOG
from app.models.service_identity import ServiceIdentity, ServiceIdentityAudit
from app.models.tenant import Tenant, TenantStatus
from app.schemas.service_identity import ServiceIdentityCreate, ServiceTokenRequest

_hasher = PasswordHasher()
_READ_ONLY_SUFFIXES = (":read",)


class ServiceIdentityService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: ServiceIdentityCreate, actor_user_id: int) -> tuple[ServiceIdentity, str]:
        """创建最小权限服务主体，并仅在本次响应返回随机明文凭据。"""
        tenants = sorted(set(payload.tenant_ids))
        found = set(
            self.session.scalars(
                select(Tenant.id).where(
                    Tenant.id.in_(tenants), Tenant.status == TenantStatus.ACTIVE.value
                )
            ).all()
        )
        if found != set(tenants):
            raise AppError("租户范围包含不存在或已停用租户", code=40071, status_code=400)
        audiences = sorted(set(payload.allowed_audiences))
        known_audiences = set(settings.jwt_audience_list) - {"neorvion-iam"}
        if not set(audiences).issubset(known_audiences):
            raise AppError("服务 Audience 不在允许目录", code=40072, status_code=400)
        scopes = sorted(set(payload.allowed_scopes))
        known_scopes = {item[0] for item in PERMISSION_CATALOG}
        if not set(scopes).issubset(known_scopes) or any(
            not scope.endswith(_READ_ONLY_SUFFIXES) for scope in scopes
        ):
            raise AppError("SERVICE 仅允许申请目录内只读权限", code=40073, status_code=400)
        secret = f"nsvc_{secrets.token_urlsafe(40)}"
        row = ServiceIdentity(
            public_id=f"svc_{uuid4().hex}",
            name=payload.name.strip(),
            subject_type="SERVICE",
            tenant_ids=tenants,
            allowed_audiences=audiences,
            allowed_scopes=scopes,
            allowed_resources=payload.allowed_resources,
            secret_hash=_hasher.hash(secret),
            credential_version=1,
            status="ACTIVE",
            expires_at=payload.expires_at,
            created_by=actor_user_id,
        )
        self.session.add(row)
        self.session.flush()
        self._audit(row.id, "CREATED", actor_user_id, {"tenants": tenants, "scopes": scopes})
        self.session.commit()
        self.session.refresh(row)
        return row, secret

    def issue(self, payload: ServiceTokenRequest) -> tuple[str, int]:
        """校验凭据与授权交集后签发五分钟内有效的目标 Audience Token。"""
        row = self.session.scalar(
            select(ServiceIdentity).where(ServiceIdentity.public_id == payload.service_id)
        )
        if row is None:
            raise AppError("服务凭据无效", code=40170, status_code=401)
        try:
            valid = _hasher.verify(row.secret_hash, payload.client_secret)
        except (VerifyMismatchError, InvalidHashError):
            valid = False
        if not valid:
            self._audit(row.id, "TOKEN_REJECTED", None, {"reason": "credential"})
            self.session.commit()
            raise AppError("服务凭据无效", code=40170, status_code=401)
        row = self._active(payload.service_id)
        if payload.tenant_id not in set(row.tenant_ids or []):
            raise AppError("服务身份不能访问该租户", code=40370, status_code=403)
        if payload.audience not in set(row.allowed_audiences or []):
            raise AppError("服务身份不能申请该 Audience", code=40371, status_code=403)
        scopes = sorted(set(payload.scopes))
        if not set(scopes).issubset(set(row.allowed_scopes or [])):
            raise AppError("服务身份不能申请该 Scope", code=40372, status_code=403)
        resources = self._bounded_resources(payload.resources, row.allowed_resources or {})
        ttl = min(300, settings.service_token_expire_seconds)
        token, jti = get_jwt_signer().sign_service(
            service_id=row.public_id,
            ttl=timedelta(seconds=ttl),
            audiences=["neorvion-iam", payload.audience],
            tenant_scope=[payload.tenant_id],
            scopes=scopes,
            resources=resources,
            credential_version=row.credential_version,
        )
        row.last_used_at = datetime.now(UTC)
        self._audit(
            row.id,
            "TOKEN_ISSUED",
            None,
            {"tenant_id": payload.tenant_id, "audience": payload.audience, "scopes": scopes},
            token_id=jti,
        )
        self.session.commit()
        return token, ttl

    def rotate(self, public_id: str, actor_user_id: int) -> tuple[ServiceIdentity, str]:
        row = self._get(public_id)
        secret = f"nsvc_{secrets.token_urlsafe(40)}"
        row.secret_hash = _hasher.hash(secret)
        row.credential_version += 1
        row.status = "ACTIVE"
        row.revoked_at = None
        self._audit(row.id, "CREDENTIAL_ROTATED", actor_user_id, {"version": row.credential_version})
        self.session.commit()
        self.session.refresh(row)
        return row, secret

    def revoke(self, public_id: str, actor_user_id: int) -> ServiceIdentity:
        row = self._get(public_id)
        row.status = "REVOKED"
        row.revoked_at = datetime.now(UTC)
        row.credential_version += 1
        self._audit(row.id, "REVOKED", actor_user_id, {"version": row.credential_version})
        self.session.commit()
        self.session.refresh(row)
        return row

    def authorize_claims(self, claims, *, tenant_id: int, audience: str, scopes: list[str]):
        """以 IAM 数据库实时复核 Token，确保吊销、轮换和租户停用立即生效。"""
        row = self._active(claims.service_id)
        if claims.credential_version != row.credential_version:
            raise AppError("服务凭据已轮换", code=40171, status_code=401)
        if tenant_id not in claims.tenant_scope or tenant_id not in set(row.tenant_ids or []):
            raise AppError("服务身份不能访问该租户", code=40370, status_code=403)
        if audience not in claims.audience or audience not in set(row.allowed_audiences or []):
            raise AppError("服务 Token Audience 不匹配", code=40371, status_code=403)
        if not set(scopes).issubset(set(claims.scopes)) or not set(scopes).issubset(
            set(row.allowed_scopes or [])
        ):
            raise AppError("服务 Token Scope 不足", code=40372, status_code=403)
        tenant = self.session.get(Tenant, tenant_id)
        if tenant is None or tenant.status != TenantStatus.ACTIVE.value:
            raise AppError("租户已停用", code=40311, status_code=403)
        row.last_used_at = datetime.now(UTC)
        self._audit(row.id, "TOKEN_AUTHORIZED", None, {"tenant_id": tenant_id, "audience": audience})
        self.session.commit()
        return row

    @staticmethod
    def require_resources(claims, requested: dict[str, list[str]]) -> None:
        """资源范围采用逐类子集校验；空请求不扩大 Token 已签名范围。"""
        if claims.resources and not requested:
            raise AppError("受限服务 Token 必须声明本次资源", code=40373, status_code=403)
        for kind, values in requested.items():
            granted = set(claims.resources.get(kind, ()))
            if not {str(item) for item in values}.issubset(granted):
                raise AppError("服务 Token 资源范围不足", code=40373, status_code=403)

    def list(self) -> list[ServiceIdentity]:
        return list(self.session.scalars(select(ServiceIdentity).order_by(ServiceIdentity.id)).all())

    def _active(self, public_id: str) -> ServiceIdentity:
        row = self._get(public_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        if row.status != "ACTIVE" or row.revoked_at is not None:
            raise AppError("服务身份已停用", code=40172, status_code=401)
        if row.expires_at is not None and row.expires_at <= now:
            raise AppError("服务身份已过期", code=40173, status_code=401)
        return row

    def _get(self, public_id: str) -> ServiceIdentity:
        row = self.session.scalar(select(ServiceIdentity).where(ServiceIdentity.public_id == public_id))
        if row is None:
            raise AppError("服务身份不存在", code=40470, status_code=404)
        return row

    @staticmethod
    def _bounded_resources(requested: dict[str, list[str]], allowed: dict) -> dict[str, list[str]]:
        if allowed and not requested:
            raise AppError("服务身份必须申请明确资源范围", code=40373, status_code=403)
        result: dict[str, list[str]] = {}
        for kind, values in requested.items():
            allowed_values = {str(item) for item in allowed.get(kind, [])}
            wanted = {str(item) for item in values}
            if not wanted.issubset(allowed_values):
                raise AppError("服务身份资源范围越权", code=40373, status_code=403)
            result[kind] = sorted(wanted)
        return result

    def _audit(
        self,
        service_identity_id: int,
        event_type: str,
        actor_user_id: int | None,
        detail: dict,
        *,
        token_id: str = "",
    ) -> None:
        self.session.add(
            ServiceIdentityAudit(
                service_identity_id=service_identity_id,
                event_type=event_type,
                actor_user_id=actor_user_id,
                token_id_hash=hashlib.sha256(token_id.encode()).hexdigest() if token_id else "",
                safe_detail=detail,
            )
        )
