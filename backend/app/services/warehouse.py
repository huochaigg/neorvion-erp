"""仓库主数据。Repository 不 commit；写操作由本层提交。"""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseType
from app.repositories.warehouse import WarehouseRepository
from app.schemas.warehouse import (
    WarehouseCreate,
    WarehouseListOut,
    WarehouseOut,
    WarehouseStatusUpdate,
    WarehouseUpdate,
)
from app.services.authorization import AuthorizationService

_UNAVAILABLE = "仓库不存在或不可访问"
_WAREHOUSE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_AUTO_PREFIX = "WH"
_AUTO_WIDTH = 10
_OPTIONAL_TEXT_FIELDS = (
    "country_code",
    "province",
    "city",
    "address",
    "contact_name",
    "contact_phone",
    "remark",
)


class WarehouseService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.warehouses = WarehouseRepository(session, context.tenant_id)

    def list_warehouses(
        self,
        *,
        q: str | None,
        warehouse_type: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> WarehouseListOut:
        self.auth.require_all(self.context, (PermissionCode.WAREHOUSE_READ,))
        if warehouse_type and warehouse_type not in {item.value for item in WarehouseType}:
            raise AppError("仓库类型不合法", code=40060, status_code=400)
        if status and status not in {item.value for item in WarehouseStatus}:
            raise AppError("仓库状态不合法", code=40061, status_code=400)
        rows, total = self.warehouses.list_page(
            q=(q or "").strip() or None,
            warehouse_type=warehouse_type,
            status=status,
            page=page,
            page_size=page_size,
        )
        return WarehouseListOut(
            items=[self._to_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_warehouse(self, warehouse_id: int) -> WarehouseOut:
        self.auth.require_all(self.context, (PermissionCode.WAREHOUSE_READ,))
        return self._to_out(self._require(warehouse_id))

    def create_warehouse(self, payload: WarehouseCreate) -> WarehouseOut:
        """新增本租户仓库。第一个仓库自动成为默认仓库。

        编码：未填写时先 INSERT 空 code，flush 拿到自增 id，再写成 WH + 10 位数字。
        不要用 MAX(code)+1：删除后会复用号段，并发下也不安全。
        默认仓库：两个管理员同时建「第一个仓库」时，都可能读到 count=0。
        因此先锁 tenants 行，再数仓库。别的企业的 tenants 行不受影响。
        """
        self.auth.require_all(self.context, (PermissionCode.WAREHOUSE_CREATE,))
        warehouse_type = self._normalize_type(payload.type)
        status = self._normalize_status(payload.status or WarehouseStatus.ACTIVE.value)
        custom_code = self._normalize_optional_code(payload.code)
        country_code = self._normalize_country(payload.country_code)

        try:
            # 锁本租户行，串行化「是否第一个仓库」的判断，避免并发插入两个默认仓。
            if self.warehouses.lock_tenant() is None:
                raise AppError(_UNAVAILABLE, code=40440, status_code=404)
            is_first = self.warehouses.count_in_tenant() == 0
            if is_first and status != WarehouseStatus.ACTIVE.value:
                raise AppError(
                    "第一个仓库必须为启用状态，并自动成为默认仓库",
                    code=40061,
                    status_code=400,
                    data={"error": "FIRST_WAREHOUSE_MUST_BE_ACTIVE"},
                )
            if custom_code is not None and self.warehouses.get_by_code(custom_code) is not None:
                raise AppError("仓库编码已存在", code=40940, status_code=409)

            warehouse = Warehouse(
                tenant_id=self.context.tenant_id,
                name=payload.name,
                code=custom_code,
                type=warehouse_type,
                country_code=country_code,
                province=payload.province,
                city=payload.city,
                address=payload.address,
                contact_name=payload.contact_name,
                contact_phone=payload.contact_phone,
                is_default=is_first,
                status=status,
                remark=payload.remark,
            )
            self.warehouses.add(warehouse)
            # flush 把 INSERT 发给 MySQL，拿到 autoincrement id，事务仍未提交。
            self.session.flush()
            if warehouse.code is None:
                warehouse.code = self._auto_code(warehouse.id)
            if not warehouse.code:
                raise AppError("仓库编码生成失败", code=50021, status_code=500)
            self.session.commit()
            self.session.refresh(warehouse)
        except IntegrityError:
            # 应用层查重与提交之间可能有并发写入；UNIQUE(tenant_id, code) 是最后防线。
            self.session.rollback()
            raise AppError("仓库编码已存在", code=40940, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(warehouse)

    def update_warehouse(self, warehouse_id: int, payload: WarehouseUpdate) -> WarehouseOut:
        """编辑仓库档案。不改 code / is_default / status。

        PATCH 不提交 code：保持原值，不能重新生成。创建后编码只读。
        """
        self.auth.require_all(self.context, (PermissionCode.WAREHOUSE_UPDATE,))
        warehouse = self._require(warehouse_id)
        if payload.name is not None:
            warehouse.name = payload.name
        if payload.type is not None:
            warehouse.type = self._normalize_type(payload.type)
        for field in _OPTIONAL_TEXT_FIELDS:
            if field not in payload.model_fields_set:
                continue
            value = getattr(payload, field)
            if field == "country_code":
                value = self._normalize_country(value)
            setattr(warehouse, field, value)
        try:
            self.session.commit()
            self.session.refresh(warehouse)
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(warehouse)

    def change_status(self, warehouse_id: int, payload: WarehouseStatusUpdate) -> WarehouseOut:
        """启用或禁用仓库。默认仓库不能处于 DISABLED。

        默认仓若还有其他启用仓：必须先切换默认，再禁用。
        即使是最后一个仓库，也不能禁用默认仓，否则会出现 is_default=true 且停用。
        """
        self.auth.require_all(self.context, (PermissionCode.WAREHOUSE_DISABLE,))
        status = self._normalize_status(payload.status)
        warehouse = self._require(warehouse_id)
        if status == WarehouseStatus.DISABLED.value and warehouse.is_default:
            raise AppError(
                "请先将其他仓库设为默认仓库，再禁用当前仓库。",
                code=40063,
                status_code=400,
                data={"error": "DEFAULT_WAREHOUSE_CANNOT_DISABLE"},
            )
        warehouse.status = status
        try:
            self.session.commit()
            self.session.refresh(warehouse)
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(warehouse)

    def set_default_warehouse(self, warehouse_id: int) -> WarehouseOut:
        """把指定仓库设为当前租户的唯一默认仓库。

        为什么需要事务：
        默认仓切换包含两步：旧默认 is_default=false，新默认 is_default=true。
        如果先 commit 旧默认再改新默认，中间窗口该租户会没有默认仓；
        若第二步失败，旧默认已经没了，数据处于不一致状态。必须同一事务提交。

        为什么要加行锁：
        两个管理员同时把 A、B 设为默认时，若不加锁，双方都可能先读到「当前默认是 C」，
        然后各自把 C 改成 false、把自己的目标改成 true，最终 A、B 都是默认。
        SELECT ... FOR UPDATE 锁住本租户全部仓库行后，后到的事务必须等前一个提交，
        再读到已经更新过的默认标记。

        为什么不能用 Redis 分布式锁：
        默认仓只是本租户几行 MySQL 记录，InnoDB 行锁足够；引入 Redis 会多一个故障点。

        为什么必须带 tenant_id：
        锁条件和更新条件都含 tenant_id，A 企业改默认不会碰到 B 企业的行。
        """
        self.auth.require_all(self.context, (PermissionCode.WAREHOUSE_UPDATE,))
        try:
            locked = self.warehouses.lock_all_in_tenant()
            target = next((row for row in locked if row.id == warehouse_id), None)
            if target is None:
                raise AppError(_UNAVAILABLE, code=40440, status_code=404)
            if target.status != WarehouseStatus.ACTIVE.value:
                raise AppError(
                    "停用状态的仓库不能设为默认仓库",
                    code=40065,
                    status_code=400,
                    data={"error": "DISABLED_WAREHOUSE_CANNOT_SET_DEFAULT"},
                )
            for row in locked:
                row.is_default = row.id == target.id
            self.session.commit()
            self.session.refresh(target)
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self._to_out(target)

    def delete_warehouse(self, warehouse_id: int) -> None:
        """删除尚未被业务引用的仓库。

        默认仓不是该租户最后一个仓库时禁止删除，必须先切换默认。
        已被库存引用的仓库禁止物理删除，只允许停用。
        """
        self.auth.require_all(self.context, (PermissionCode.WAREHOUSE_DELETE,))
        try:
            locked = self.warehouses.lock_all_in_tenant()
            warehouse = next((row for row in locked if row.id == warehouse_id), None)
            if warehouse is None:
                raise AppError(_UNAVAILABLE, code=40440, status_code=404)
            self._assert_not_referenced(warehouse)
            if warehouse.is_default and len(locked) > 1:
                raise AppError(
                    "请先将其他仓库设为默认仓库，再删除当前仓库。",
                    code=40064,
                    status_code=400,
                    data={"error": "DEFAULT_WAREHOUSE_CANNOT_DELETE"},
                )
            self.warehouses.delete(warehouse)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "仓库已被业务单据引用，不能删除。",
                code=40066,
                status_code=400,
                data={"error": "WAREHOUSE_IN_USE"},
            ) from None
        except Exception:
            self.session.rollback()
            raise

    def _require(self, warehouse_id: int) -> Warehouse:
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError(_UNAVAILABLE, code=40440, status_code=404)
        return warehouse

    def _assert_not_referenced(self, warehouse: Warehouse) -> None:
        """有库存台账就不能删仓库，否则流水会失去仓库维度。采购/订单引用留给后续版本。"""
        from app.repositories.inventory import InventoryRepository

        used = InventoryRepository(self.session, self.context.tenant_id).count_by_warehouse(
            warehouse.id,
        )
        if used > 0:
            raise AppError(
                "仓库已被库存引用，不能删除。",
                code=40066,
                status_code=400,
                data={"error": "WAREHOUSE_IN_USE"},
            )

    @staticmethod
    def _auto_code(warehouse_id: int) -> str:
        return f"{_AUTO_PREFIX}{warehouse_id:0{_AUTO_WIDTH}d}"

    @staticmethod
    def _normalize_type(value: str) -> str:
        if value not in {item.value for item in WarehouseType}:
            raise AppError("仓库类型不合法", code=40060, status_code=400)
        return value

    @staticmethod
    def _normalize_status(value: str) -> str:
        if value not in {item.value for item in WarehouseStatus}:
            raise AppError("仓库状态不合法", code=40061, status_code=400)
        return value

    @staticmethod
    def _normalize_country(value: str | None) -> str | None:
        if value is None:
            return None
        if not _COUNTRY_CODE.fullmatch(value):
            raise AppError("国家代码必须是 ISO 两位字母，例如 CN", code=40062, status_code=400)
        return value

    @staticmethod
    def _normalize_optional_code(code: str | None) -> str | None:
        if code is None:
            return None
        normalized = code.strip().upper()
        if not normalized:
            return None
        if not _WAREHOUSE_CODE.fullmatch(normalized):
            raise AppError("仓库编码不合法", code=40067, status_code=400)
        return normalized

    @staticmethod
    def _to_out(row: Warehouse) -> WarehouseOut:
        return WarehouseOut(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            code=row.code or "",
            type=row.type,
            country_code=row.country_code,
            province=row.province,
            city=row.city,
            address=row.address,
            contact_name=row.contact_name,
            contact_phone=row.contact_phone,
            is_default=row.is_default,
            status=row.status,
            remark=row.remark,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
