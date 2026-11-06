/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_VERSION?: string;
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
