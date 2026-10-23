import axios from 'axios';
import { TENANT_HEADER, type ApiResponse } from '@neorvion/shared';
import { shellProps } from '@/runtime';
import { useCopilotStore } from '@/store';

export type ErpOptionKind = 'supplier'|'customer'|'warehouse'|'sku';
export interface ErpOption { value:number; label:string }

const erpApi = axios.create({
  baseURL: import.meta.env.VITE_ERP_API_BASE_URL || (import.meta.env.PROD ? '' : 'http://localhost:8011'),
  timeout: 8000,
});
erpApi.interceptors.request.use((config) => {
  const token = shellProps().token;
  const tenantId = useCopilotStore.getState().tenantId;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (tenantId) config.headers[TENANT_HEADER] = String(tenantId);
  return config;
});

export async function listErpOptions(kind:ErpOptionKind, q:string, signal?:AbortSignal):Promise<ErpOption[]> {
  const path = kind === 'supplier' ? '/api/v1/suppliers' : kind === 'customer' ? '/api/v1/customers' : kind === 'warehouse' ? '/api/v1/warehouses' : '/api/v1/product-skus';
  const response = await erpApi.get<ApiResponse<{items:Array<Record<string,unknown>>}>>(path, {
    signal, params:{q:q||undefined,status:kind==='sku'?undefined:'ACTIVE',page:1,page_size:20},
  });
  if (response.data.code !== 0) throw new Error(response.data.message);
  return response.data.data.items.map((item) => ({
    value:Number(item.id),
    label:kind === 'sku'
      ? `${String(item.sku_code ?? '')} / ${String(item.product_name ?? '')} / ${String(item.name ?? '')}`
      : `${String(item.name ?? '')}${item.code ? ` (${String(item.code)})` : ''}`,
  }));
}
