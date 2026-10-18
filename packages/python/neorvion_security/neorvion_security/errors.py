"""安全校验失败。调用方映射为 HTTP 401/403，不得在失败时放行。"""


class SecurityError(Exception):
    """JWT、JWKS、快照或权限校验失败。"""

    def __init__(
        self,
        message: str,
        *,
        code: int = 40102,
        status_code: int = 401,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
