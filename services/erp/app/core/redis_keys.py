"""Redis Key 规范。租户缓存必须带 tenant_id；认证会话保持全局。"""


def tenant_cache_key(tenant_id: int, *parts: str | int) -> str:
    """例如 erp:tenant:1001:product:1，禁止写成 erp:product:1。"""
    labels = ":".join(str(part) for part in parts)
    return f"erp:tenant:{tenant_id}:{labels}"


def auth_refresh_key(jti: str) -> str:
    """登录会话属于用户，不属于某个租户。切换企业时不要改这个键。"""
    return f"auth:refresh:{jti}"


def auth_challenge_key(challenge_id: str) -> str:
    return f"auth:challenge:{challenge_id}"
