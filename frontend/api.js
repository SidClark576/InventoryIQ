// ── AUTH FUNCTIONS ────────────────────────────────────────────

function checkQuota(res) {
  if (res.status === 429) {
    throw new Error('API quota exceeded — please wait a moment and try again, or contact your administrator.');
  }
}

function check401(res) {
  if (res.status === 401) {
    sessionStorage.clear();
    window.location.href = 'login.html?expired=1';
    throw new Error('Session expired. Please log in again.');
  }
}

function getCurrentUserID() {
  return sessionStorage.getItem('userEmail') || '';
}

// Headers for all proxied requests — includes session token for server-side validation
function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-Session-Token': sessionStorage.getItem('sessionToken') || ''
  };
}

async function authRegister(email, password) {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  return { status: res.status, data: await res.json() };
}

async function authLogin(email, password) {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  return { status: res.status, data: await res.json() };
}

// ── INVENTORY FUNCTIONS ───────────────────────────────────────

async function getAllItems() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/items?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/items`;
  const res = await fetch(url, {
    headers: authHeaders()
  });

  checkQuota(res);
  check401(res);
  const raw = await res.text();
  let data = [];
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = [];
    }
  }

  if (!res.ok) {
    const errMsg = data && typeof data === "object" ? data.error : null;
    throw new Error(errMsg || "Failed to fetch items");
  }

  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return [];
}

async function getDeletedItems() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/items?userID=${encodeURIComponent(userID)}&deleted=true`
    : `${CONFIG.API_ENDPOINT}/items?deleted=true`;
  const res = await fetch(url, { headers: authHeaders() });
  checkQuota(res);
  check401(res);
  const raw = await res.text();
  let data = [];
  if (raw) {
    try { data = JSON.parse(raw); } catch { data = []; }
  }
  if (!res.ok) {
    const errMsg = data && typeof data === 'object' ? data.error : null;
    throw new Error(errMsg || 'Failed to fetch deleted items');
  }
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return [];
}

async function addItem(item) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(item)
  });
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to add item");
  return data;
}

async function updateItem(itemID, updates, version) {
  // Sprint 3: If-Match header required for optimistic locking.
  // Pass the item's current `version` field so the server can detect concurrent edits.
  const headers = { ...authHeaders() };
  if (version !== undefined && version !== null) {
    headers['If-Match'] = String(version);
  }
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(updates)
  });
  checkQuota(res);
  check401(res);
  let data;
  try {
    data = await res.json();
  } catch {
    data = { message: "Update failed" };
  }
  if (res.status === 412) throw new Error('Version conflict — item was modified elsewhere. Refresh and try again.');
  if (res.status === 428) throw new Error('Missing version — please refresh the page and try again.');
  if (!res.ok) throw new Error(data.error || data.message || "Failed to update item");
  return data;
}

async function restoreItem(itemID) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}/restore`, {
    method: "POST",
    headers: authHeaders()
  });
  checkQuota(res);
  check401(res);
  let data;
  try {
    data = await res.json();
  } catch {
    data = { message: "Restore failed" };
  }
  if (!res.ok) throw new Error(data.error || data.message || "Failed to restore item");
  return data;
}

async function deleteItem(itemID) {
  // Adding a timestamp query param bypasses any cached failed CORS preflight responses in the browser
  // userID is sent for server-side ownership validation
  const userID = getCurrentUserID();
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}?_cb=${Date.now()}&userID=${encodeURIComponent(userID)}`, {
    method: "DELETE",
    headers: authHeaders(),
    cache: "no-store",
    mode: "cors"
  });
  checkQuota(res);
  check401(res);
  let data;
  try {
    data = await res.json();
  } catch {
    data = { message: "Delete failed" };
  }
  if (!res.ok) throw new Error(data.error || data.message || "Failed to delete item");
  return data;
}

async function getInsights() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/insights?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/insights`;

  const res = await fetch(url, {
    headers: authHeaders()
  });
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch insights");
  return data;
}

async function getTransactions() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/transactions?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/transactions`;
  const res = await fetch(url, { headers: authHeaders() });
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch transactions");
  return Array.isArray(data) ? data : [];
}

async function getCategories() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/categories?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/categories`;
  const res = await fetch(url, {
    headers: authHeaders()
  });
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch categories");
  return Array.isArray(data) ? data : [];
}

async function lookupBarcode(code) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/barcode/${encodeURIComponent(code)}`, {
    headers: authHeaders()
  });
  checkQuota(res);
  check401(res);
  if (res.status === 404) return null;
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Barcode lookup failed');
  return data;
}

async function deleteCategory(categoryName) {
  const userID = getCurrentUserID();
  const res = await fetch(
    `${CONFIG.API_ENDPOINT}/categories/${encodeURIComponent(categoryName)}?userID=${encodeURIComponent(userID)}`,
    {
      method: "DELETE",
      headers: authHeaders()
    }
  );
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to delete category");
  return data;
}

// ── BULK IMPORT + FORECAST FUNCTIONS ─────────────────────────

async function bulkImport(rows, idemKey) {
  const headers = { ...authHeaders() };
  if (idemKey) headers['X-Idempotency-Key'] = idemKey;
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/import`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ rows })
  });
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Bulk import failed');
  return data;
}

async function uploadImportCSV(file) {
  const presignRes = await fetch(
    `${CONFIG.API_ENDPOINT}/import/presign?filename=${encodeURIComponent(file.name)}`,
    { headers: authHeaders() }
  );
  checkQuota(presignRes);
  check401(presignRes);
  const { presignedUrl, jobId } = await presignRes.json();
  if (!presignedUrl) throw new Error('Failed to get upload URL');

  // PUT directly to S3 — presigned URL is self-authenticating, no auth headers needed
  const s3Res = await fetch(presignedUrl, {
    method: 'PUT',
    headers: { 'Content-Type': 'text/csv' },
    body: file
  });
  if (!s3Res.ok) throw new Error(`S3 upload failed: ${s3Res.status}`);

  return jobId;
}

async function getImportJob(jobId) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/import/${encodeURIComponent(jobId)}`, {
    headers: authHeaders()
  });
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to fetch import job');
  return data;
}

async function getForecast() {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/forecast`, {
    headers: authHeaders()
  });
  checkQuota(res);
  check401(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to fetch forecast');
  return data;
}