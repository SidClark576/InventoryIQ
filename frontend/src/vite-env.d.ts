/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set by `npm run dev:local` to the local API runner (scripts/local_api.py). */
  readonly VITE_API_BASE?: string;
}
