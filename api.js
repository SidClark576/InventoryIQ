// ── AUTH FUNCTIONS ────────────────────────────────────────────

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
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    headers: { "x-api-key": CONFIG.API_KEY }
  });
  return await res.json();
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
  return await res.json();
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
  return await res.json();
}

async function deleteItem(itemID) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}`, {
    method: "DELETE",
    headers: { "x-api-key": CONFIG.API_KEY }
  });
  return await res.json();
}

async function getInsights() {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/insights`, {
    headers: { "x-api-key": CONFIG.API_KEY }
  });
  return await res.json();
}