import type {
  ApiResponse,
  ProductCreatePayload,
  ProductDetail,
  ProductList,
  ProductSku,
  ProductSkuInput,
  ProductSkuUpdatePayload,
  ProductUpdatePayload,
} from '@neorvion/shared';
import { apiClient, unwrapApi } from './client';

export function fetchProducts(
  params: {
    q?: string;
    skuCode?: string;
    categoryId?: number;
    brandId?: number;
    status?: string;
    page: number;
    pageSize: number;
  },
  signal?: AbortSignal,
) {
  return unwrapApi(
    apiClient.get<ApiResponse<ProductList>>('/api/v1/products', {
      params: {
        q: params.q || undefined,
        sku_code: params.skuCode || undefined,
        category_id: params.categoryId || undefined,
        brand_id: params.brandId || undefined,
        status: params.status || undefined,
        page: params.page,
        page_size: params.pageSize,
      },
      signal,
    }),
  );
}

export function fetchProduct(productId: number, signal?: AbortSignal) {
  return unwrapApi(
    apiClient.get<ApiResponse<ProductDetail>>(`/api/v1/products/${productId}`, { signal }),
  );
}

export function createProduct(payload: ProductCreatePayload) {
  return unwrapApi(apiClient.post<ApiResponse<ProductDetail>>('/api/v1/products', payload));
}

export function updateProduct(productId: number, payload: ProductUpdatePayload) {
  return unwrapApi(
    apiClient.patch<ApiResponse<ProductDetail>>(`/api/v1/products/${productId}`, payload),
  );
}

export function addProductSku(productId: number, payload: ProductSkuInput) {
  return unwrapApi(
    apiClient.post<ApiResponse<ProductSku>>(`/api/v1/products/${productId}/skus`, payload),
  );
}

export function updateProductSku(
  productId: number,
  skuId: number,
  payload: ProductSkuUpdatePayload,
) {
  return unwrapApi(
    apiClient.patch<ApiResponse<ProductSku>>(
      `/api/v1/products/${productId}/skus/${skuId}`,
      payload,
    ),
  );
}

export function deleteProductSku(productId: number, skuId: number) {
  return unwrapApi(
    apiClient.delete<ApiResponse<null>>(`/api/v1/products/${productId}/skus/${skuId}`),
  );
}
