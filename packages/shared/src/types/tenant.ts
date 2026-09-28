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
  joined_at: string;
  display_name: string;
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
  order: '订单管理',
  inventory: '库存管理',
  purchase: '采购管理',
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
  tenantMemberRead: 'tenant:member:read',
  tenantMemberManage: 'tenant:member:manage',
  tenantRoleRead: 'tenant:role:read',
  tenantRoleManage: 'tenant:role:manage',
  productRead: 'product:read',
  productCreate: 'product:create',
  productUpdate: 'product:update',
  orderRead: 'order:read',
  inventoryRead: 'inventory:read',
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
