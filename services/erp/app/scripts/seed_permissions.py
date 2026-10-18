"""ERP 不再维护权限目录。请到 IAM 执行：

    uv run --directory services/iam python -m app.scripts.seed_permissions
"""


def main() -> None:
    raise SystemExit(
        "权限目录已迁到 IAM。请执行："
        "uv run --directory services/iam python -m app.scripts.seed_permissions"
    )


if __name__ == "__main__":
    main()
