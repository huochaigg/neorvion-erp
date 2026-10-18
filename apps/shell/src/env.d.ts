/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_ERP_ENTRY: string;
  readonly VITE_KNOWLEDGE_ENTRY: string;
  readonly VITE_IAM_ENTRY: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
