// `npm run dev:local` points the app at the local API runner; everything else uses the live API.
const API_BASE =
  import.meta.env.VITE_API_BASE || 'https://d1g2j27343.execute-api.us-east-1.amazonaws.com/prod';

export const API_ENDPOINT = `${API_BASE}/proxy`;
export const AUTH_ENDPOINT = `${API_BASE}/auth`;

export const CONFIG = {
  API_ENDPOINT,
  AUTH_ENDPOINT,
} as const;
