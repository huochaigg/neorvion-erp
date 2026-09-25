"""RSA 公钥发放。与 JWT / Argon2id 独立，不要求登录。"""

from app.core import challenge_store
from app.core.config import settings
from app.core.rsa_crypto import RSA_ALGORITHM, get_rsa_store
from app.schemas.auth import PublicKeyOut


def issue_public_key(key_id: str | None = None) -> PublicKeyOut:
    """返回可用公钥和一次性 challenge。私钥永不返回。"""
    store = get_rsa_store()
    target_id = (key_id or "").strip() or store.current_key_id
    material = store.material_for(target_id)
    challenge_id = challenge_store.issue_challenge(material.key_id)
    return PublicKeyOut(
        key_id=material.key_id,
        public_key=material.public_pem,
        algorithm=RSA_ALGORITHM,
        challenge_id=challenge_id,
        expires_in=settings.rsa_challenge_ttl_seconds,
    )
