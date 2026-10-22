import logging
import sys

from app.core.config import settings
from app.core.context import get_current_tenant_id, get_current_user_id
from app.core.request_id import get_request_id


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.tenant_id = get_current_tenant_id() or "-"
        record.user_id = get_current_user_id() or "-"
        return True


def setup_logging() -> None:
    """配置请求上下文日志，禁止记录 Token、模型密钥和完整对话正文。"""
    level = logging.DEBUG if settings.app_env == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s %(levelname)s [%(name)s] "
            "rid=%(request_id)s tenant=%(tenant_id)s user=%(user_id)s %(message)s"
        ),
        stream=sys.stdout,
        force=True,
    )
    context_filter = RequestContextFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(context_filter)

