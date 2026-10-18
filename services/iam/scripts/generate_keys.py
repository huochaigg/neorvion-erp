"""生成密码传输 RSA 与 JWT RS256 两套独立密钥。私钥不要提交 Git、不要打印内容。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.rsa_crypto import write_rsa_key_pair

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 IAM RSA 传输密钥与 JWT 签名密钥")
    parser.add_argument("--rsa-key-id", default="v1")
    parser.add_argument("--jwt-key-id", default="jwt-v1")
    parser.add_argument("--jwt-dir", default="v1", help="相对 secrets/jwt 的目录，需与 JWT_PRIVATE_KEY_PATH 一致")
    args = parser.parse_args()
    rsa_dir = ROOT / "secrets" / "rsa" / args.rsa_key_id
    jwt_dir = ROOT / "secrets" / "jwt" / args.jwt_dir
    write_rsa_key_pair(rsa_dir / "private.pem", rsa_dir / "public.pem")
    write_rsa_key_pair(jwt_dir / "private.pem", jwt_dir / "public.pem")
    print(f"RSA_KEY_ID={args.rsa_key_id}")
    print(f"RSA_PRIVATE_KEY_PATH={rsa_dir / 'private.pem'}")
    print(f"JWT_KEY_ID={args.jwt_key_id}")
    print(f"JWT_PRIVATE_KEY_PATH={jwt_dir / 'private.pem'}")
    print("两套私钥必须独立。不要把 pem 提交到 Git。")


if __name__ == "__main__":
    main()
