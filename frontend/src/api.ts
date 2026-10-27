import { CONFIG } from './config';
import {
  clearSession,
  getCurrentOrg,
  getSessionToken,
  setCurrentOrg,
  setCurrentOrgName,
  setCurrentRole,
  setLocalLogout,
  type Role,
} from './session';

export type { Role } from './session';

export type StatusData<T = Record<string, unknown>> = {
  status: number;
  data: T;
};

export type InventoryItem = {
  itemID?: string;
  name?: string;
  category?: string;
  quantity?: number;
  price?: number;
  lowStockThreshold?: number;
  version?: number;
  barcode?: string;
  description?: string;
  userID?: string;
  orgID?: string;
  deletedAt?: string;
  deletedBy?: string;
  [key: string]: unknown;
};

type ErrorBody = { error?: string; message?: string };

/** Error with the HTTP status, so callers can tell a 412 conflict or a 403/404 missing route apart. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** POST /items and PUT /items/{id} return `{ message, item }`; `item` carries the new `version`. */
export function itemFromResponse(data: Record<string, unknown>): InventoryItem | null {
  const item = data.item;
  return item && typeof item === 'object' ? (item as InventoryItem) : null;
}

function errorField(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  return (data as ErrorBody).error ?? null;
}

function errorOrMessage(data: unknown): string | undefined {
  if (!data || typeof data !== 'object') return undefined;
  const body = data as ErrorBody;
  return body.error || body.message;
}

export function checkQuota(res: Response): void {
  if (res.status === 429) {
    throw new Error(
      'API quota exceeded — please wait a moment and try again, or contact your administrator.',
    );
  }
}

/** Preview sign-in is for `npm run dev` only (not `dev:local`, which has a real local backend): a production build or the app shell (https://localhost) must show the login form. */
export function isLocalPreview(): boolean {
  return import.meta.env.DEV && !import.meta.env.VITE_API_BASE;
}

/** api.ts can't reach the router; App.tsx listens for this and navigates to /login?expired=1. */
export const SESSION_EXPIRED_EVENT = 'iq:session-expired';

export function check401(res: Response): void {
  if (res.status === 401) {
    if (isLocalPreview() && !getSessionToken()) {
      throw new Error('Local preview has no session. Sign in to load live data.');
    }
    clearSession();
    // A real session expired during local preview: show the login form, not the fake preview user.
    if (isLocalPreview()) setLocalLogout();
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    throw new Error('Session expired. Please log in again.');
  }
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Session-Token': getSessionToken(),
  };
  // Only send a selected org. An empty X-IQ-Org still triggers a browser preflight
  // for a header the API Gateway allow-list did not include, which surfaces as
  // "Failed to fetch". Proxy treats a missing header as "no org".
  const org = getCurrentOrg();
  if (org) headers['X-IQ-Org'] = org;
  return headers;
}

let orgReady: Promise<void> | null = null;

export async function ensureOrgContext(): Promise<void> {
  if (getCurrentOrg()) return;
  if (orgReady) return orgReady;
  orgReady = (async () => {
    const data = await getOrgs();
    const orgs = (data && data.orgs) || [];
    if (!orgs.length) return;
    const first = orgs[0];
    if (!first) return;
    await switchOrg(first.orgID);
    if (first.name) setCurrentOrgName(first.name);
  })().catch((err: unknown) => {
    orgReady = null;
    throw err;
  });
  return orgReady;
}

export async function readyHeaders(
  extra?: Record<string, string>,
): Promise<Record<string, string>> {
  try {
    await ensureOrgContext();
  } catch {
    /* org tables may not be live yet */
  }
  return extra ? Object.assign({}, authHeaders(), extra) : authHeaders();
}

export async function authRegister(
  email: string,
  password: string,
): Promise<StatusData> {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  let data: Record<string, unknown>;
  try {
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    data = { message: 'Internal Server Error' };
  }
  return { status: res.status, data };
}

export async function authLogin(
  email: string,
  password: string,
): Promise<StatusData> {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  let data: Record<string, unknown>;
  try {
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    data = { message: 'Internal Server Error' };
  }
  return { status: res.status, data };
}

export async function getAllItems(): Promise<InventoryItem[]> {
  const url = `${CONFIG.API_ENDPOINT}/items`;
  const res = await fetch(url, {
    headers: await readyHeaders(),
  });

  checkQuota(res);
  check401(res);
  const raw = await res.text();
  let data: unknown = [];
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = [];
    }
  }

  if (!res.ok) {
    const errMsg = errorField(data);
    throw new Error(errMsg || 'Failed to fetch items');
  }

  if (Array.isArray(data)) return data as InventoryItem[];
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: InventoryItem[] }).items;
  }
  return [];
}

export async function getDeletedItems(): Promise<InventoryItem[]> {
  const url = `${CONFIG.API_ENDPOINT}/items?deleted=true`;
  const res = await fetch(url, { headers: await readyHeaders() });
  checkQuota(res);
  check401(res);
  const raw = await res.text();
  let data: unknown = [];
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = [];
    }
  }
  if (!res.ok) {
    const errMsg = errorField(data);
    throw new Error(errMsg || 'Failed to fetch deleted items');
  }
  if (Array.isArray(data)) return data as InventoryItem[];
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: InventoryItem[] }).items;
  }
  return [];
}

/** `idemKey` lets the server drop a duplicate POST when a retry follows a lost response. */
export async function addItem(item: Record<string, unknown>, idemKey?: string): Promise<Record<string, unknown>> {
  const headers = await readyHeaders();
  if (idemKey) headers['Idempotency-Key'] = idemKey;
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    method: 'POST',
    headers,
    body: JSON.stringify(item),
  });
  checkQuota(res);
  check401(res);
  const data = (await res.json()) as ErrorBody;
  if (!res.ok) throw new ApiError(res.status, data.error || 'Failed to add item');
  return data as Record<string, unknown>;
}

export async function updateItem(
  itemID: string,
  updates: Record<string, unknown>,
  version?: number | string | null,
): Promise<Record<string, unknown>> {
  // Sprint 3: If-Match header required for optimistic locking.
  // Pass the item's current `version` field so the server can detect concurrent edits.
  const headers = await readyHeaders();
  if (version !== undefined && version !== null) {
    headers['If-Match'] = String(version);
  }
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${encodeURIComponent(itemID)}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(updates),
  });
  checkQuota(res);
  check401(res);
  let data: ErrorBody;
  try {
    data = (await res.json()) as ErrorBody;
  } catch {
    data = { message: 'Update failed' };
  }
  if (res.status === 412) {
    throw new ApiError(412, 'Version conflict — item was modified elsewhere. Refresh and try again.');
  }
  if (res.status === 428) {
    throw new ApiError(428, 'Missing version — please refresh the page and try again.');
  }
  if (!res.ok) throw new ApiError(res.status, data.error || data.message || 'Failed to update item');
  return data as Record<string, unknown>;
}

export async function restoreItem(itemID: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${encodeURIComponent(itemID)}/restore`, {
    method: 'POST',
    headers: await readyHeaders(),
  });
  checkQuota(res);
  check401(res);
  let data: ErrorBody;
  try {
    data = (await res.json()) as ErrorBody;
  } catch {
    data = { message: 'Restore failed' };
  }
  if (!res.ok) throw new ApiError(res.status, data.error || data.message || 'Failed to restore item');
  return data as Record<string, unknown>;
}

export async function deleteItem(itemID: string): Promise<Record<string, unknown>> {
  // Adding a timestamp query param bypasses any cached failed CORS preflight responses in the browser
  // userID is sent automatically via session token server-side
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${encodeURIComponent(itemID)}?_cb=${Date.now()}`, {
    method: 'DELETE',
    headers: await readyHeaders(),
    cache: 'no-store',
    mode: 'cors',
  });
  checkQuota(res);
  check401(res);
  let data: ErrorBody;
  try {
    data = (await res.json()) as ErrorBody;
  } catch {
    data = { message: 'Delete failed' };
  }
  if (!res.ok) throw new ApiError(res.status, data.error || data.message || 'Failed to delete item');
  return data as Record<string, unknown>;
}

export async function getInsights(): Promise<Record<string, unknown>> {
  const url = `${CONFIG.API_ENDPOINT}/insights`;

  const res = await fetch(url, {
    headers: await readyHeaders(),
  });
  checkQuota(res);
  check401(res);
  const data = (await res.json()) as ErrorBody;
  if (!res.ok) throw new Error(data.error || 'Failed to fetch insights');
  return data as Record<string, unknown>;
}

/** Newest 200 rows; with `since` (UTC ISO), every row on or after it. */
export async function getTransactions(since?: string): Promise<unknown[]> {
  const query = since ? `?since=${encodeURIComponent(since)}` : "";
  const url = `${CONFIG.API_ENDPOINT}/transactions${query}`;
  const res = await fetch(url, { headers: await readyHeaders() });
  checkQuota(res);
  check401(res);
  const data: unknown = await res.json();
  if (!res.ok) throw new Error(errorField(data) || 'Failed to fetch transactions');
  return Array.isArray(data) ? data : [];
}

export async function getCategories(): Promise<string[]> {
  const url = `${CONFIG.API_ENDPOINT}/categories`;
  const res = await fetch(url, {
    headers: await readyHeaders(),
  });
  checkQuota(res);
  check401(res);
  const data: unknown = await res.json();
  if (!res.ok) throw new Error(errorField(data) || 'Failed to fetch categories');
  return Array.isArray(data) ? (data as string[]) : [];
}

export async function lookupBarcode(code: string): Promise<Record<string, unknown> | null> {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/barcode/${encodeURIComponent(code)}`, {
    headers: await readyHeaders(),
  });
  checkQuota(res);
  check401(res);
  if (res.status === 404) return null;
  const data = (await res.json()) as ErrorBody;
  if (!res.ok) throw new Error(data.error || 'Barcode lookup failed');
  return data as Record<string, unknown>;
}

export async function deleteCategory(categoryName: string): Promise<Record<string, unknown>> {
  const res = await fetch(
    `${CONFIG.API_ENDPOINT}/categories/${encodeURIComponent(categoryName)}`,
    {
      method: 'DELETE',
      headers: await readyHeaders(),
    },
  );
  checkQuota(res);
  check401(res);
  const data = (await res.json()) as ErrorBody;
  if (!res.ok) throw new Error(data.error || 'Failed to delete category');
  return data as Record<string, unknown>;
}

export async function bulkImport(
  rows: unknown[],
  idemKey?: string,
): Promise<Record<string, unknown>> {
  const headers = await readyHeaders();
  if (idemKey) headers['Idempotency-Key'] = idemKey;
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/import`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ rows }),
  });
  checkQuota(res);
  check401(res);
  let data: ErrorBody;
  try {
    data = (await res.json()) as ErrorBody;
  } catch {
    data = {};
  }
  if (!res.ok) throw new ApiError(res.status, data.error || data.message || 'Bulk import failed');
  return data as Record<string, unknown>;
}

export async function uploadImportCSV(file: File): Promise<unknown> {
  const presignRes = await fetch(
    `${CONFIG.API_ENDPOINT}/import/presign?filename=${encodeURIComponent(file.name)}`,
    { headers: await readyHeaders() },
  );
  checkQuota(presignRes);
  check401(presignRes);
  if (!presignRes.ok) throw new ApiError(presignRes.status, 'Failed to get upload URL');
  const { presignedUrl, jobId } = (await presignRes.json()) as {
    presignedUrl?: string;
    jobId?: unknown;
  };
  if (!presignedUrl) throw new Error('Failed to get upload URL');

  // PUT directly to S3 — presigned URL is self-authenticating, no auth headers needed
  const s3Res = await fetch(presignedUrl, {
    method: 'PUT',
    headers: { 'Content-Type': 'text/csv' },
    body: file,
  });
  if (!s3Res.ok) throw new Error(`S3 upload failed: ${s3Res.status}`);

  return jobId;
}

export async function getImportJob(jobId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/import/${encodeURIComponent(jobId)}`, {
    headers: await readyHeaders(),
  });
  checkQuota(res);
  check401(res);
  const data = (await res.json()) as ErrorBody;
  if (!res.ok) throw new Error(data.error || 'Failed to fetch import job');
  return data as Record<string, unknown>;
}

export type OrgRecord = {
  orgID: string;
  name?: string;
  role?: Role | string;
};

export type OrgsResponse = {
  orgs?: OrgRecord[];
  [key: string]: unknown;
};

async function orgJson<T = Record<string, unknown>>(
  url: string,
  opts: RequestInit,
  failMsg: string,
): Promise<T> {
  const res = await fetch(url, { headers: authHeaders(), ...opts });
  checkQuota(res);
  check401(res);
  let data: unknown;
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok) throw new Error(errorOrMessage(data) || failMsg);
  return data as T;
}

export async function getOrgs(): Promise<OrgsResponse> {
  return orgJson<OrgsResponse>(`${CONFIG.API_ENDPOINT}/orgs`, {}, 'Failed to load organizations');
}

export async function switchOrg(orgID: string): Promise<Record<string, unknown>> {
  const data = await orgJson<Record<string, unknown>>(
    `${CONFIG.API_ENDPOINT}/orgs/${encodeURIComponent(orgID)}/switch`,
    { method: 'POST' },
    'Failed to switch organization',
  );
  setCurrentOrg(orgID);
  if (typeof data.role === 'string' && data.role) setCurrentRole(data.role);
  return data;
}

export async function getMembers(orgID: string): Promise<Record<string, unknown>> {
  return orgJson(
    `${CONFIG.API_ENDPOINT}/orgs/${encodeURIComponent(orgID)}/members`,
    {},
    'Failed to load members',
  );
}

export async function inviteMember(
  orgID: string,
  email: string,
  role: Role | string,
): Promise<Record<string, unknown>> {
  return orgJson(
    `${CONFIG.API_ENDPOINT}/orgs/${encodeURIComponent(orgID)}/invites`,
    { method: 'POST', body: JSON.stringify({ email, role }) },
    'Failed to send invite',
  );
}

export async function acceptInvite(token: string): Promise<Record<string, unknown>> {
  return orgJson(
    `${CONFIG.API_ENDPOINT}/org-invites/${encodeURIComponent(token)}/accept`,
    { method: 'POST' },
    'Failed to accept invite',
  );
}
