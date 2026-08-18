/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_NEO4J_URI: string;
  readonly VITE_NEO4J_USER: string;
  readonly VITE_NEO4J_PASSWORD: string;
  readonly VITE_NEO4J_DATABASE: string;
  readonly VITE_API_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
