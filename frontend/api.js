// ── AUTH FUNCTIONS ────────────────────────────────────────────

function getAuthHeaders() {
  /**
   * Returns standard headers for proxied API requests.
   * Includes JWT token from sessionStorage in Authorization header.
   * Used by all inventory endpoints (/proxy/* routes).
   */
  const token = sessionStorage.getItem('iq_jwt_token') || '';
  return {
    "Content-Type": "application/json",
    "Authorization": token ? `Bearer ${token}` : ''
  };
}

function check401(res) {
  /**
   * Detects 401 Unauthorized responses and clears JWT token.
   * Called on every proxied API response to handle token expiry.
   * Redirects to login.html so user re-authenticates.
   */
  if (res.status === 401) {
    sessionStorage.removeItem('iq_jwt_token');
    sessionStorage.removeItem('userEmail');
    window.location.href = 'login.html';
  }
}

function checkQuota(res) {
  if (res.status === 429) {
    throw new Error('API quota exceeded — please wait a moment and try again, or contact your administrator.');
  }
}

function getCurrentUserID() {
  return sessionStorage.getItem('userEmail') || '';
}

async function authRegister(email, password) {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  const data = await res.json();
  console.log('[authRegister] status:', res.status, 'data:', data);
  return { status: res.status, data };
}

async function authLogin(email, password) {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  const data = await res.json();
  console.log('[authLogin] status:', res.status, 'data:', data);
  return { status: res.status, data };
}

// ── INVENTORY FUNCTIONS ───────────────────────────────────────

async function getAllItems() {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    headers: getAuthHeaders()
  });

  check401(res);
  checkQuota(res);
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

async function addItem(item) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(item)
  });
  check401(res);
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to add item");
  return data;
}

async function updateItem(itemID, updates) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}`, {
    method: "PUT",
    headers: getAuthHeaders(),
    body: JSON.stringify(updates)
  });
  check401(res);
  checkQuota(res);
  let data;
  try {
    data = await res.json();
  } catch {
    data = { message: "Update failed" };
  }
  if (!res.ok) throw new Error(data.error || data.message || "Failed to update item");
  return data;
}

async function deleteItem(itemID) {
  // Adding a timestamp query param bypasses any cached failed CORS preflight responses in the browser
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}?_cb=${Date.now()}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
    cache: "no-store",
    mode: "cors"
  });
  check401(res);
  checkQuota(res);
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
  const res = await fetch(`${CONFIG.API_ENDPOINT}/insights`, {
    headers: getAuthHeaders()
  });
  check401(res);
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch insights");
  return data;
}

async function getTransactions() {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/transactions`, {
    headers: getAuthHeaders()
  });
  check401(res);
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch transactions");
  return Array.isArray(data) ? data : [];
}

async function getCategories() {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/categories`, {
    headers: getAuthHeaders()
  });
  check401(res);
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch categories");
  return Array.isArray(data) ? data : [];
}

async function deleteCategory(categoryName) {
  const res = await fetch(
    `${CONFIG.API_ENDPOINT}/categories/${encodeURIComponent(categoryName)}`,
    {
      method: "DELETE",
      headers: getAuthHeaders()
    }
  );
  check401(res);
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to delete category");
  return data;
}