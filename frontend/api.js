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
   * Detects 401 Unauthorized responses and handles token expiry.
   * If the JWT is still valid (not expired), the 401 is a config error
   * (e.g. JWT_SECRET mismatch between Lambdas) — do NOT redirect.
   * Only redirect to login.html when the token is actually expired or absent.
   */
  if (res.status === 401) {
    const token = sessionStorage.getItem('iq_jwt_token');
    if (token) {
      try {
        const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        const payload = JSON.parse(atob(b64));
        const now = Math.floor(Date.now() / 1000);
        if (payload.exp && payload.exp > now) {
          // Token not expired — 401 is a server config error, not session expiry.
          // Log it but don't redirect — page will show data loading errors instead.
          console.error('Proxy returned 401 but token is not expired. Check JWT_SECRET in Proxy Lambda.');
          return;
        }
      } catch {
        // Can't decode token — treat as expired, fall through to redirect.
      }
    }
    sessionStorage.removeItem('iq_jwt_token');
    sessionStorage.removeItem('userEmail');
    sessionStorage.setItem('auth_redirect_reason', 'session_expired');
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
  let data;
  try {
    data = await res.json();
  } catch {
    data = { message: "Server error. Please try again." };
  }
  console.log('[authRegister] status:', res.status, 'data:', data);
  return { status: res.status, data };
}

async function authLogin(email, password) {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  let data;
  try {
    data = await res.json();
  } catch {
    data = { message: "Server error. Please try again." };
  }
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