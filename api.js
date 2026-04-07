// ── AUTH FUNCTIONS ────────────────────────────────────────────

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
    headers: { "x-api-key": CONFIG.API_KEY }
  });

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
    headers: {
      "Content-Type": "application/json",
      "x-api-key": CONFIG.API_KEY
    },
    body: JSON.stringify(item)
  });
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to add item");
  return data;
}

async function updateItem(itemID, updates) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": CONFIG.API_KEY
    },
    body: JSON.stringify(updates)
  });
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
    headers: { 
      "x-api-key": CONFIG.API_KEY,
      "Content-Type": "application/json"
    },
    cache: "no-store",
    mode: "cors"
  });
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
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/insights?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/insights`;

  const res = await fetch(url, {
    headers: { "x-api-key": CONFIG.API_KEY }
  });
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch insights");
  return data;
}

async function getTransactions() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/transactions?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/transactions`;
  const res = await fetch(url, { headers: { "x-api-key": CONFIG.API_KEY } });
  checkQuota(res);
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
    headers: { "x-api-key": CONFIG.API_KEY }
  });
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to fetch categories");
  return Array.isArray(data) ? data : [];
}

async function deleteCategory(categoryName) {
  const userID = getCurrentUserID();
  const res = await fetch(
    `${CONFIG.API_ENDPOINT}/categories/${encodeURIComponent(categoryName)}?userID=${encodeURIComponent(userID)}`,
    {
      method: "DELETE",
      headers: { "x-api-key": CONFIG.API_KEY }
    }
  );
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to delete category");
  return data;
}