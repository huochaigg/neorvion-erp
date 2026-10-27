from datetime import timedelta

import pytest
from app.core.exceptions import AppError
from app.schemas.governance import ProviderOut
from app.services.insights import InsightService
from app.services.quotas import usage_tokens
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from neorvion_security import JwtVerifier, LocalJwtSigner, SecurityError


def _signer() -> LocalJwtSigner:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return LocalJwtSigner(
        private_pem=private_pem,
        kid="v11-test",
        issuer="neorvion-iam",
        audiences=["neorvion-iam"],
    )


def test_service_token_has_signed_identity_scope_and_resources() -> None:
    signer = _signer()
    token, _ = signer.sign_service(
        service_id="svc_scheduler",
        ttl=timedelta(minutes=5),
        audiences=["neorvion-iam", "neorvion-erp"],
        tenant_scope=[7],
        scopes=["inventory:read"],
        resources={"warehouse": ["3"]},
        credential_version=4,
    )
    claims = JwtVerifier(
        issuer="neorvion-iam",
        audience="neorvion-erp",
        static_keys={"v11-test": signer.public_pem},
    ).verify_access(token)
    assert claims.subject_type == "SERVICE"
    assert claims.user_id == 0
    assert claims.service_id == "svc_scheduler"
    assert claims.tenant_scope == (7,)
    assert claims.scopes == ("inventory:read",)
    assert claims.resources == {"warehouse": ("3",)}
    assert claims.credential_version == 4


def test_service_token_rejects_wrong_audience() -> None:
    signer = _signer()
    token, _ = signer.sign_service(
        service_id="svc_scheduler",
        ttl=timedelta(minutes=5),
        audiences=["neorvion-iam", "neorvion-erp"],
        tenant_scope=[7],
        scopes=["inventory:read"],
    )
    verifier = JwtVerifier(
        issuer="neorvion-iam",
        audience="neorvion-knowledge",
        static_keys={"v11-test": signer.public_pem},
    )
    with pytest.raises(SecurityError):
        verifier.verify_access(token)


def test_provider_response_has_reference_but_no_secret() -> None:
    fields = ProviderOut.model_fields
    assert "secret_env_name" in fields
    assert "secret_configured" in fields
    assert "api_key" not in fields
    assert "client_secret" not in fields


def test_unknown_usage_is_not_coerced_to_zero() -> None:
    assert usage_tokens(None) is None
    assert usage_tokens({"prompt_tokens": None, "completion_tokens": None}) is None
    assert usage_tokens({"prompt_tokens": 10, "completion_tokens": 3}) == 13


def test_insight_analysis_accepts_only_json_object() -> None:
    assert InsightService._analysis_json('{"fact_summary":"ok"}') == {"fact_summary": "ok"}
    with pytest.raises(AppError):
        InsightService._analysis_json("ordinary text")
    with pytest.raises(AppError):
        InsightService._analysis_json("[]")
