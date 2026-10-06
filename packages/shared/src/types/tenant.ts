/** 与后端 `TenantOut` / `MemberOut` / `TenantContextOut` 对齐。 */

export interface Tenant {
  id: number;
  name: string;
  code: string;
  status: string;
  created_by: number;
  created_at: string;
  updated_at: string;
  my_role: string;
  my_status: string;
  is_owner: boolean;
}

export interface TenantContextInfo {
  user_id: number;
  tenant_id: number;
  member_id: number;
  is_owner: boolean;
  role: string;
  permission_codes: string[];
}

export interface TenantMemberRole {
  id: number;
  code: string;
  name: string;
  is_system: boolean;
}

export interface PermissionInfo {
  id: number;
  code: string;
  name: string;
  module: string;
  description: string;
  deprecated?: boolean;
}

export type PermissionResourceType = 'DIRECTORY' | 'MENU' | 'ACTION';

export interface PermissionTreeNode {
  key: string;
  title: string;
  type: PermissionResourceType;
  permission_id: number | null;
  permission_code: string | null;
  children: PermissionTreeNode[];
}

export interface RoleInfo {
  id: number;
  tenant_id: number;
  name: string;
  code: string;
  description: string;
  is_system: boolean;
  created_at: string;
  updated_at: string;
  permissions: PermissionInfo[];
  member_count: number;
}

export interface TenantMember {
  id: number;
  tenant_id: number;
  user_id: number;
  role: string;
  status: string;
  display_name: string;
  member_display_name?: string | null;
  user_display_name?: string;
  email: string;
  is_owner: boolean;
  roles: TenantMemberRole[];
}

export interface TenantMemberList {
  items: TenantMember[];
  total: number;
  page: number;
  page_size: number;
}

export interface TenantMemberDetail extends TenantMember {
  permission_codes: string[];
  permissions: PermissionInfo[];
}

export interface TenantCreatePayload {
  name: string;
  code?: string | null;
}

export interface MemberCreatePayload {
  email: string;
  role_ids?: number[];
}

export interface MemberAccountCreatePayload {
  display_name: string;
  email: string;
  role_ids?: number[];
}

export interface MemberCreated extends TenantMember {
  temporary_password?: string | null;
}

export interface MemberRolesUpdatePayload {
  role_ids: number[];
}

export interface MemberUpdatePayload {
  display_name?: string | null;
  status?: string;
}

export interface RoleCreatePayload {
  name: string;
  code: string;
  description?: string;
  permission_ids?: number[];
}

export interface RoleUpdatePayload {
  name?: string;
  description?: string;
}

export const PERMISSION_MODULE_LABELS: Record<string, string> = {
  tenant: '企业管理',
  product: '商品管理',
  warehouse: '仓库管理',
  order: '订单管理',
  customer: '客户管理',
  inventory: '库存管理',
  purchase: '采购管理',
  supplier: '供应商管理',
};

export const TENANT_HEADER = 'X-Tenant-ID';

export const TENANT_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const MEMBER_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const PERMISSION_CODE = {
  tenantRead: 'tenant:read',
  tenantUpdate: 'tenant:update',
  tenantMemberRead: 'tenant:member:read',
  tenantMemberCreate: 'tenant:member:create',
  tenantMemberUpdate: 'tenant:member:update',
  tenantMemberRoleUpdate: 'tenant:member:role:update',
  tenantMemberDisable: 'tenant:member:disable',
  tenantMemberRemove: 'tenant:member:remove',
  tenantMemberManage: 'tenant:member:manage',
  tenantRoleRead: 'tenant:role:read',
  tenantRoleCreate: 'tenant:role:create',
  tenantRoleUpdate: 'tenant:role:update',
  tenantRoleDelete: 'tenant:role:delete',
  tenantRolePermissionUpdate: 'tenant:role:permission:update',
  tenantRoleManage: 'tenant:role:manage',
  tenantPermissionRead: 'tenant:permission:read',
  productRead: 'product:read',
  productCreate: 'product:create',
  productUpdate: 'product:update',
  productDelete: 'product:delete',
  orderRead: 'order:read',
  orderCreate: 'order:create',
  orderUpdate: 'order:update',
  orderSubmit: 'order:submit',
  orderAudit: 'order:audit',
  orderCancel: 'order:cancel',
  customerRead: 'customer:read',
  customerCreate: 'customer:create',
  customerUpdate: 'customer:update',
  customerDisable: 'customer:disable',
  customerDelete: 'customer:delete',
  inventoryRead: 'inventory:read',
  inventoryInitialize: 'inventory:initialize',
  inventoryAdjust: 'inventory:adjust',
  inventoryTransactionRead: 'inventory:transaction:read',
  inventoryInbound: 'inventory:inbound',
  inventoryOutbound: 'inventory:outbound',
  warehouseRead: 'warehouse:read',
  warehouseCreate: 'warehouse:create',
  warehouseUpdate: 'warehouse:update',
  warehouseDisable: 'warehouse:disable',
  warehouseDelete: 'warehouse:delete',
  purchaseRead: 'purchase:read',
  purchaseCreate: 'purchase:create',
  purchaseUpdate: 'purchase:update',
  purchaseSubmit: 'purchase:submit',
  purchaseAudit: 'purchase:audit',
  purchaseCancel: 'purchase:cancel',
  supplierRead: 'supplier:read',
  supplierCreate: 'supplier:create',
  supplierUpdate: 'supplier:update',
  supplierDisable: 'supplier:disable',
  supplierDelete: 'supplier:delete',
} as const;

export type PermissionMode = 'any' | 'all';

export interface MyPermissions {
  roles: string[];
  permissions: string[];
}

export const TENANT_ERROR_CODE = {
  missingContext: 40030,
  forbidden: 40310,
  notFound: 40410,
} as const;
