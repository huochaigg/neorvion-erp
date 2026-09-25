import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """配置应用日志。禁止在日志中输出 Token、密码等敏感信息。"""
    level = logging.DEBUG if settings.app_env == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
        force=True,
    )
