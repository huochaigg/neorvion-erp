"""JWT RS256 密钥。与登录密码 RSA-OAEP 私钥完全独立。"""

from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from neorvion_security.jwt import LocalJwtSigner

from app.core.config import settings
from app.core.exceptions import AppError

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def resolve_key_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return _BACKEND_DIR / path


def _load_private_pem(path: Path) -> bytes:
    if not path.is_file():
        raise AppError("服务端未配置 JWT 私钥", code=50015, status_code=500)
    loaded: PrivateKeyTypes = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(loaded, rsa.RSAPrivateKey):
        raise AppError("服务端 JWT 密钥无效", code=50016, status_code=500)
    return path.read_bytes()


@lru_cache
def get_jwt_signer() -> LocalJwtSigner:
    private_pem = _load_private_pem(resolve_key_path(settings.jwt_private_key_path))
    return LocalJwtSigner(
        private_pem=private_pem,
        kid=settings.jwt_key_id.strip(),
        issuer=settings.jwt_issuer,
        audiences=settings.jwt_audience_list,
    )


def previous_public_pem() -> tuple[bytes, str] | None:
    previous_id = settings.jwt_previous_key_id.strip()
    previous_path = settings.jwt_previous_private_key_path.strip()
    if not previous_id or not previous_path:
        return None
    pem = _load_private_pem(resolve_key_path(previous_path))
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        return None
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return public, previous_id


def build_jwks() -> dict:
    signer = get_jwt_signer()
    previous = previous_public_pem()
    if previous is None:
        return signer.jwks()
    return signer.jwks(previous[0], previous[1])
