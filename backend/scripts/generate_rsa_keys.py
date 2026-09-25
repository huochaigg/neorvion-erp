"""生成开发用 RSA 密钥对。私钥不要提交 Git、不要打印。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.rsa_crypto import write_rsa_key_pair

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "secrets" / "rsa"


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 RSA-2048 PKCS#8 私钥与 SPKI 公钥")
    parser.add_argument("--key-id", default="v1", help="密钥目录名，对应 RSA_KEY_ID")
    parser.add_argument("--out-dir", default=str(DEFAULT_DIR), help="输出根目录")
    args = parser.parse_args()

    target = Path(args.out_dir) / args.key_id
    private_path = target / "private.pem"
    public_path = target / "public.pem"
    write_rsa_key_pair(private_path, public_path)
    print(f"RSA_KEY_ID={args.key_id}")
    print(f"RSA_PRIVATE_KEY_PATH={private_path}")
    print(f"RSA_PUBLIC_KEY_PATH={public_path}")
    print("请把以上路径写入 backend/.env，不要把私钥提交到 Git。")


if __name__ == "__main__":
    main()
