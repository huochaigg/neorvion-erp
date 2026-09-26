import type { QueryClient } from '@tanstack/react-query';

let queryClient: QueryClient | null = null;

export function registerQueryClient(client: QueryClient) {
  queryClient = client;
}

export function getRegisteredQueryClient() {
  return queryClient;
}
