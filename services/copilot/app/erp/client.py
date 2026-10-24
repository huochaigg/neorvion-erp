from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError


class ErpApiClient:
    """复用连接的 ERP 只读客户端；身份与租户仍由 ERP 独立校验。"""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: float,
        read_timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None,
        access_token: str,
        tenant_id: int,
        request_id: str = "",
    ) -> Any:
        """调用固定 ERP 路径；不接受模型提供的 URL、Token 或租户。"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": str(tenant_id),
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            response = await self._client.get(
                f"{self.base_url}{path}", params=params, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise AppError("ERP 查询超时", code=50470, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("ERP 服务暂时不可用", code=50270, status_code=502) from exc
        if response.status_code in {401, 403}:
            raise AppError("无权查询该 ERP 数据", code=40370, status_code=403)
        if response.status_code == 404:
            raise AppError("ERP 数据不存在或无权访问", code=40470, status_code=404)
        if response.status_code == 429:
            raise AppError("ERP 查询过于频繁", code=42970, status_code=429)
        if response.status_code >= 500:
            raise AppError("ERP 服务暂时不可用", code=50270, status_code=502)
        if response.status_code >= 400:
            raise AppError("ERP 查询参数无效", code=40070, status_code=400)
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError("ERP 返回了无效响应", code=50271, status_code=502) from exc
        if not isinstance(payload, dict) or payload.get("code") != 0 or "data" not in payload:
            raise AppError("ERP 返回了无效响应", code=50271, status_code=502)
        return payload["data"]

    async def preview(
        self,
        path: str,
        *,
        payload: dict[str, Any],
        access_token: str,
        tenant_id: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        """仅允许调用 Action Registry 固定的无副作用预检路径。"""
        allowed = {
            "/api/v1/action-previews/purchase-order",
            "/api/v1/action-previews/sales-order",
            "/api/v1/action-previews/inventory-transfer",
        }
        if path not in allowed:
            raise AppError("ERP 预检路径未注册", code=50072, status_code=500)
        headers = {"Authorization": f"Bearer {access_token}", "X-Tenant-ID": str(tenant_id)}
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            response = await self._client.post(
                f"{self.base_url}{path}", json=payload, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise AppError("ERP 预检超时", code=50472, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("ERP 预检服务暂时不可用", code=50272, status_code=502) from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise AppError("ERP 预检返回了无效响应", code=50273, status_code=502) from exc
        if response.status_code in {401, 403}:
            raise AppError("无权预检该业务动作", code=40372, status_code=403)
        if response.status_code in {400, 404, 422}:
            message = (
                body.get("message", "ERP 业务校验未通过")
                if isinstance(body, dict)
                else "ERP 业务校验未通过"
            )
            return {
                "valid": False,
                "blocking_errors": [{"code": str(body.get("code", 40072)), "message": message}],
                "warnings": [],
                "missing_fields": [],
                "normalized_payload": payload,
                "preview_summary": {},
                "resource_versions": {},
            }
        if response.status_code == 429:
            raise AppError("ERP 预检过于频繁", code=42972, status_code=429)
        if response.status_code >= 500:
            raise AppError("ERP 预检服务暂时不可用", code=50272, status_code=502)
        if (
            not isinstance(body, dict)
            or body.get("code") != 0
            or not isinstance(body.get("data"), dict)
        ):
            raise AppError("ERP 预检返回了无效响应", code=50273, status_code=502)
        return body["data"]

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _execution_claim(
        *,
        tenant_id: int,
        user_id: int,
        action_type: str,
        execution_key: str,
        revision: int,
        payload_hash: str,
        expires_at: int,
    ) -> str:
        return "\n".join(
            map(
                str,
                (
                    tenant_id,
                    user_id,
                    action_type,
                    execution_key,
                    revision,
                    payload_hash,
                    expires_at,
                ),
            )
        )

    async def execute(
        self,
        path: str,
        *,
        execution_key: str,
        action_type: str,
        revision: int,
        payload_hash: str,
        payload: dict[str, Any],
        user_id: int,
        access_token: str,
        tenant_id: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        """调用固定 ERP 写接口；短期 HMAC 授权与用户 JWT/权限由 ERP 双重校验。"""
        allowed = {
            "/api/v1/action-executions/purchase-order",
            "/api/v1/action-executions/sales-order",
            "/api/v1/action-executions/inventory-transfer",
        }
        if path not in allowed:
            raise AppError("ERP 执行路径未注册", code=50074, status_code=500)
        secret = settings.erp_execution_secret.get_secret_value()
        if not secret:
            raise AppError("Copilot 未配置 ERP 执行授权", code=50374, status_code=503)
        expires_at = int(time.time()) + settings.erp_execution_authorization_ttl_seconds
        claim = self._execution_claim(
            tenant_id=tenant_id,
            user_id=user_id,
            action_type=action_type,
            execution_key=execution_key,
            revision=revision,
            payload_hash=payload_hash,
            expires_at=expires_at,
        )
        signature = hmac.new(secret.encode(), claim.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": str(tenant_id),
            "X-Copilot-Execution-Signature": signature,
            "X-Copilot-Execution-Expires": str(expires_at),
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        body = {
            "execution_key": execution_key,
            "action_type": action_type,
            "proposal_revision": revision,
            "payload_hash": payload_hash,
            "payload": payload,
        }
        try:
            response = await self._client.post(
                f"{self.base_url}{path}",
                json=body,
                headers=headers,
                timeout=settings.erp_execution_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise AppError("ERP 执行结果未知", code=50474, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("ERP 执行结果未知", code=50274, status_code=502) from exc
        return self._parse_execution_response(response)

    async def execution_receipt(
        self, execution_key: str, *, access_token: str, tenant_id: int, request_id: str = ""
    ) -> dict[str, Any] | None:
        headers = {"Authorization": f"Bearer {access_token}", "X-Tenant-ID": str(tenant_id)}
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            response = await self._client.get(
                f"{self.base_url}/api/v1/action-executions/{execution_key}", headers=headers
            )
        except httpx.HTTPError as exc:
            raise AppError("ERP 对账暂时不可用", code=50275, status_code=502) from exc
        if response.status_code == 404:
            return None
        return self._parse_execution_response(response)

    @staticmethod
    def _parse_execution_response(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise AppError("ERP 执行返回无效响应", code=50276, status_code=502) from exc
        if response.status_code in {401, 403}:
            raise AppError("无权执行 ERP 动作", code=40374, status_code=403)
        if response.status_code == 409:
            raise AppError(body.get("message", "ERP 执行幂等冲突"), code=40974, status_code=409)
        if response.status_code >= 500:
            raise AppError("ERP 执行结果未知", code=50274, status_code=502)
        if response.status_code >= 400 or not isinstance(body, dict) or body.get("code") != 0:
            raise AppError(
                body.get("message", "ERP 执行失败") if isinstance(body, dict) else "ERP 执行失败",
                code=40074,
                status_code=400,
            )
        data = body.get("data")
        if not isinstance(data, dict):
            raise AppError("ERP 执行返回无效响应", code=50276, status_code=502)
        return data


_client: ErpApiClient | None = None


def get_erp_client() -> ErpApiClient:
    global _client
    if _client is None:
        _client = ErpApiClient(
            base_url=settings.erp_base_url,
            connect_timeout=settings.erp_connect_timeout_seconds,
            read_timeout=settings.erp_read_timeout_seconds,
        )
    return _client


async def close_erp_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
