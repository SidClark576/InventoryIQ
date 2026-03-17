// api.js
function getHeaders() {
  return {
    'Content-Type': 'application/json',
    'x-api-key': CONFIG.API_KEY
  };
}

async function getAllItems() {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    headers: getHeaders()
  });
  return res.json();
}

async function addItem(item) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(item)
  });
  return res.json();
}

async function updateItem(itemId, updates) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemId}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(updates)
  });
  return res.json();
}

async function deleteItem(itemId) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemId}`, {
    method: 'DELETE',
    headers: getHeaders()
  });
  return res.json();
}

async function getInsights() {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/insights`, {
    headers: getHeaders()
  });
  return res.json();
}
