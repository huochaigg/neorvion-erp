/**
 * React Query key 必须带 tenantId，避免租户切换后串数据。
 * 全局接口（如健康检查）同样带上，便于租户切换时统一清理。
 */
export function healthQueryKey(tenantId: number | null) {
  return ['health', tenantId] as const;
}
