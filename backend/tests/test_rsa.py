import base64
import os
import subprocess
from pathlib import Path

import pytest
from app.core.rsa_crypto import (
    RSA_ALGORITHM,
    RsaCryptoError,
    _oaep,
    encrypt_with_public_pem,
    generate_rsa_key_pem,
    get_rsa_store,
)
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi.testclient import TestClient

PLAIN_PASSWORD = "Passw0rd!"
HELPER = Path(__file__).resolve().parent / "helpers" / "webcrypto_encrypt.mjs"


def test_public_private_roundtrip() -> None:
    store = get_rsa_store()
    ciphertext = encrypt_with_public_pem(store.current_public_pem, PLAIN_PASSWORD)
    assert ciphertext != PLAIN_PASSWORD
    plaintext = store.decrypt(encrypted_password=ciphertext, key_id=store.current_key_id)
    assert plaintext == PLAIN_PASSWORD


def test_wrong_private_key_cannot_decrypt() -> None:
    store = get_rsa_store()
    ciphertext = encrypt_with_public_pem(store.current_public_pem, PLAIN_PASSWORD)
    other_private_pem, _other_public_pem = generate_rsa_key_pem()
    other_private = load_pem_private_key(other_private_pem, password=None)
    raw = base64.b64decode(ciphertext)
    with pytest.raises(ValueError):
        other_private.decrypt(raw, _oaep())
    wrong_cipher = encrypt_with_public_pem(_other_public_pem.decode("utf-8"), PLAIN_PASSWORD)
    with pytest.raises(RsaCryptoError):
        store.decrypt(encrypted_password=wrong_cipher, key_id=store.current_key_id)


def test_invalid_ciphertext_raises_generic_error() -> None:
    store = get_rsa_store()
    with pytest.raises(RsaCryptoError):
        store.decrypt(encrypted_password="not-valid-base64!!", key_id=store.current_key_id)
    with pytest.raises(RsaCryptoError):
        store.decrypt(encrypted_password="A" * 344, key_id=store.current_key_id)
    with pytest.raises(RsaCryptoError):
        store.decrypt(
            encrypted_password=encrypt_with_public_pem(store.current_public_pem, PLAIN_PASSWORD),
            key_id="missing-key",
        )


def test_webcrypto_rsa_oaep_sha256_interop(client: TestClient) -> None:
    """Node Web Crypto 与后端 cryptography 使用相同 RSA-OAEP + SHA-256。"""
    material = client.get("/api/crypto/public-key").json()["data"]
    assert material["algorithm"] == RSA_ALGORITHM
    try:
        result = subprocess.run(
            ["node", str(HELPER)],
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "RSA_PUBLIC_KEY": material["public_key"],
                "RSA_PLAINTEXT": PLAIN_PASSWORD,
            },
        )
    except FileNotFoundError:
        pytest.skip("本机未安装 Node.js，跳过 Web Crypto 互通测试")
    ciphertext = result.stdout.strip()
    store = get_rsa_store()
    assert store.decrypt(encrypted_password=ciphertext, key_id=material["key_id"]) == PLAIN_PASSWORD
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "webcrypto@example.com",
            "display_name": "WebCrypto",
            "encrypted_password": ciphertext,
            "key_id": material["key_id"],
            "challenge_id": material["challenge_id"],
        },
    )
    assert response.status_code == 200, response.text
    fresh = client.get("/api/crypto/public-key").json()["data"]
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "webcrypto@example.com",
            "encrypted_password": encrypt_with_public_pem(fresh["public_key"], PLAIN_PASSWORD),
            "key_id": fresh["key_id"],
            "challenge_id": fresh["challenge_id"],
        },
    )
    assert login.status_code == 200, login.text
