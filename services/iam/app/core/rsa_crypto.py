"""RSA-OAEP（SHA-256）传输加密。与 JWT SECRET_KEY、Argon2id 哈希相互独立。"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

from app.core.config import settings
from app.core.exceptions import AppError

_BACKEND_DIR = Path(__file__).resolve().parents[2]

RSA_ALGORITHM = "RSA-OAEP-SHA256"
RSA_KEY_SIZE = 2048


class RsaCryptoError(AppError):
    """RSA 失败对外统一文案，避免泄露填充或密钥细节。"""

    def __init__(self) -> None:
        super().__init__("认证凭证无效", code=40022, status_code=400)


def generate_rsa_key_pem() -> tuple[bytes, bytes]:
    """生成 PKCS#8 私钥与 SPKI 公钥 PEM。仅供脚本和测试使用。"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_SIZE)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def write_rsa_key_pair(private_path: Path, public_path: Path) -> None:
    private_pem, public_pem = generate_rsa_key_pem()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    try:
        private_path.chmod(0o600)
    except OSError:
        pass


def resolve_key_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return _BACKEND_DIR / path


def _oaep() -> padding.OAEP:
    return padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )


def _load_private_key(path: Path) -> rsa.RSAPrivateKey:
    if not path.is_file():
        raise AppError("服务端未配置 RSA 私钥", code=50010, status_code=500)
    loaded: PrivateKeyTypes = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(loaded, rsa.RSAPrivateKey):
        raise AppError("服务端 RSA 密钥无效", code=50011, status_code=500)
    return loaded


def encrypt_with_public_pem(public_pem: str, plaintext: str) -> str:
    """测试/联调用：与浏览器 RSA-OAEP SHA-256 相同填充。"""
    public_key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise RsaCryptoError()
    cipher = public_key.encrypt(plaintext.encode("utf-8"), _oaep())
    return base64.b64encode(cipher).decode("ascii")


@dataclass(frozen=True, slots=True)
class RsaKeyMaterial:
    key_id: str
    private_key: rsa.RSAPrivateKey
    public_pem: str


class RsaKeyStore:
    """按 key_id 选择私钥。当前公钥给前端，上一把私钥用于轮换窗口。"""

    def __init__(self) -> None:
        self.current_key_id = settings.rsa_key_id.strip()
        if not self.current_key_id:
            raise AppError("未配置 RSA_KEY_ID", code=50012, status_code=500)

        current = _load_private_key(resolve_key_path(settings.rsa_private_key_path))
        public_path = settings.rsa_public_key_path.strip()
        if public_path:
            public_pem = resolve_key_path(public_path).read_text(encoding="utf-8")
        else:
            public_pem = current.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")

        self._keys: dict[str, RsaKeyMaterial] = {
            self.current_key_id: RsaKeyMaterial(
                key_id=self.current_key_id,
                private_key=current,
                public_pem=public_pem,
            )
        }

        previous_id = settings.rsa_previous_key_id.strip()
        previous_path = settings.rsa_previous_private_key_path.strip()
        if previous_id and previous_path:
            previous = _load_private_key(resolve_key_path(previous_path))
            previous_pem = previous.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
            self._keys[previous_id] = RsaKeyMaterial(
                key_id=previous_id,
                private_key=previous,
                public_pem=previous_pem,
            )

    @property
    def current_public_pem(self) -> str:
        return self._keys[self.current_key_id].public_pem

    def has_key(self, key_id: str) -> bool:
        return key_id in self._keys

    def material_for(self, key_id: str) -> RsaKeyMaterial:
        material = self._keys.get(key_id)
        if material is None:
            raise AppError("公钥不存在或已停用", code=40024, status_code=404)
        return material

    def public_pem_for(self, key_id: str) -> str:
        return self.material_for(key_id).public_pem

    def decrypt(self, *, encrypted_password: str, key_id: str) -> str:
        material = self._keys.get(key_id)
        if material is None:
            raise RsaCryptoError()
        try:
            raw = base64.b64decode(encrypted_password, validate=True)
            plain = material.private_key.decrypt(raw, _oaep())
            return plain.decode("utf-8")
        except (ValueError, TypeError, UnicodeDecodeError, InvalidTag):
            raise RsaCryptoError() from None


@lru_cache
def get_rsa_store() -> RsaKeyStore:
    return RsaKeyStore()
