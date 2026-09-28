import type {
  ApiResponse,
  Brand,
  BrandCreatePayload,
  BrandList,
  BrandUpdatePayload,
  ProductCategory,
  ProductCategoryCreatePayload,
  ProductCategoryUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchProductCategories(signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<ProductCategory[]>>('/api/v1/product-categories', { signal }),
  );
}

export function createProductCategory(payload: ProductCategoryCreatePayload) {
  return unwrapApi(
    apiClient.post<ApiResponse<ProductCategory>>('/api/v1/product-categories', payload),
  );
}

export function updateProductCategory(categoryId: number, payload: ProductCategoryUpdatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<ProductCategory>>(
      `/api/v1/product-categories/${categoryId}`,
      payload,
    ),
  );
}

export function deleteProductCategory(categoryId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/product-categories/${categoryId}`));
}

export function fetchBrands(
  params: { q?: string; status?: string; page: number; pageSize: number },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<BrandList>>('/api/v1/brands', {
      params: {
        q: params.q || undefined,
        status: params.status || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchBrandOptions(signal?: AbortSignal) {
  return unwrapApi(apiClient.get<ApiResponse<Brand[]>>('/api/v1/brands/options', { signal }));
}

export function createBrand(payload: BrandCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<Brand>>('/api/v1/brands', payload));
}

export function updateBrand(brandId: number, payload: BrandUpdatePayload) {
  return unwrapApi(apiClient.patch<ApiResponse<Brand>>(`/api/v1/brands/${brandId}`, payload));
}

export function deleteBrand(brandId: number) {
  return unwrapApi(apiClient.delete<ApiResponse<null>>(`/api/v1/brands/${brandId}`));
}
