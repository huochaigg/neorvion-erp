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
}

export interface TenantCreatePayload {
  name: string;
  code?: string | null;
}

export const TENANT_HEADER = 'X-Tenant-ID';

export const TENANT_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const MEMBER_STATUS = {
  active: 'ACTIVE',
  disabled: 'DISABLED',
} as const;

export const TENANT_ERROR_CODE = {
  missingContext: 40030,
  forbidden: 40310,
  notFound: 40410,
} as const;
