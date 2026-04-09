# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InventoryIQ is a **serverless inventory management app** on AWS. There is no local build step — changes are deployed manually to AWS Lambda (Python/Node.js functions) and S3 (frontend).

## Repository Structure

```
frontend/    # S3-deployed static assets (HTML, JS, CSS)
lambda/      # AWS Lambda functions (Python + Node.js ESM)
docs/        # Documentation and design artifacts (not deployed)
CLAUDE.md    # This file (root)
notes        # Local only — contains live keys/ARNs, never committed
```

## Deployment

**Frontend** — upload all files in `frontend/` directly to S3:
```
frontend/login.html  frontend/dashboard.html  frontend/inventory.html
frontend/add-item.html  frontend/insights.html  frontend/transactions.html
frontend/utils.js  frontend/api.js  frontend/config.js  frontend/style.css
frontend/index.html  (redirect shim → login.html)
```

**Backend** — each file in `lambda/` is a standalone Lambda function. Deploy individually via the AWS console or CLI:
```bash
zip function.zip lambda/AddItem.py && aws lambda update-function-code --function-name AddItem --zip-file fileb://function.zip
```

No package manager, no build tool, no test suite exists in this repo.

**Files NOT deployed:**
- **`notes`** — Contains live API keys, table names, and ARNs. **NEVER commit or modify.**
- `docs/` — Design artifacts and outdated docs (`AGENTS.md` predates multi-page refactor; do not rely on it)

## Architecture

```
S3 (static HTML/JS frontend)
        │ HTTPS (no x-api-key in browser)
        ▼
API Gateway /prod/proxy/*  ──►  Proxy.py Lambda
        │                        (injects x-api-key from env var,
        │                         forwards to real API Gateway stage)
        ▼
API Gateway /prod/* (x-api-key auth)
        │
  ┌─────┼──────────────┐
  ▼     ▼              ▼
DynamoDB  SNS Topic   SQS Queue
InventoryIQ  Alerts   StockQueue
Users
InventoryTransactions
```

**API key hiding via proxy:** The frontend (`config.js`) points to the `/prod/proxy` stage. `Proxy.py` runs as a Lambda behind that stage and re-issues each request to the real `/prod` stage with the `x-api-key` header injected server-side. This means the browser never sees the API key. Auth endpoints (`/auth/*`) bypass the proxy and call the real stage directly — they do not require `x-api-key`.

### API Routes → Lambda mapping
| Method | Path | Lambda |
|--------|------|--------|
| ANY | `/proxy/{proxy+}` | `Proxy.py` — forwards to real stage with injected key |
| POST | `/auth/register`, `/auth/login` | `Authentication.mjs` (Node.js ESM) |
| GET | `/items` | `GetAllItems.py` |
| POST | `/items` | `AddItem.py` |
| PUT | `/items/{itemID}` | `UpdateItem.py` |
| DELETE | `/items/{itemID}` | `DeleteItem.py` |
| GET | `/insights` | `LowItemInsight.py` |
| GET | `/transactions` | `GetTransactions.py` |
| GET | `/categories` | `GetCategories.py` |
| DELETE | `/categories/{categoryName}` | `DeleteCategory.py` |

All routes require **Lambda Proxy Integration** enabled in API Gateway.

**Category Management:**
- `GET /categories?userID=<email>` returns array of unique category strings (always includes "Uncategorized")
- `POST /categories` with body `{ userID, categoryName }` deletes category by moving all items to "Uncategorized" (idempotent, prevents deletion of "Uncategorized" itself)

## Key Conventions

- **Auth:** Passwords hashed with `crypto.scryptSync` (Node.js) + random salt. Login returns a UUID session token stored in `sessionStorage` — there is no server-side token validation after login. All inventory endpoints require `x-api-key`, which is injected by `Proxy.py` server-side — `api.js` does **not** send `x-api-key` from the browser; auth endpoints bypass the proxy entirely.
- **SNS subscription on auth:** On `/register`, `Authentication.mjs` immediately calls `SNS.Subscribe` with the user's email. On `/login`, it paginates through `ListSubscriptionsByTopic` and only re-subscribes if the email has no confirmed or pending subscription. New users see the message: "Please check your email to confirm your alert subscription."
- **Multi-user isolation:** Items are scoped by `userID` (the user's email) stored on each DynamoDB item. `GET /items`, `GET /insights`, and `GET /transactions` require `?userID=` — if omitted, they return an empty result or 400. `userID` is trusted from the client request body (no server-side ownership check on writes).
- **Decimal handling:** DynamoDB returns `Decimal` types — all Python Lambdas convert to `float` before `json.dumps`.
- **CORS:** All Lambdas return `Access-Control-Allow-Origin: *`. The frontend `deleteItem` call appends `?_cb=<timestamp>` with `cache: "no-store"` to avoid stale CORS preflight caches.
- **Low stock logic:** An item is "low stock" when `quantity <= lowStockThreshold`. Out-of-stock is `quantity == 0`. `LowItemInsight.py` publishes SNS + SQS on GET, but only once per user per `ALERT_COOLDOWN_HOURS` (default 24h). Cooldown state is stored as a sentinel DynamoDB item with `itemID='alert_meta#<userID>'` and `userID='__system__'` — these are never returned by normal inventory scans (which filter by real user email).
- **`name` is a DynamoDB reserved word** — `UpdateItem.py` uses the `#nm` expression alias when updating it.
- **Transaction logging:** `AddItem.py`, `UpdateItem.py`, and `DeleteItem.py` all write a record to `InventoryTransactions` after every mutation. `UpdateItem.py` reads the item first to capture `quantityBefore`, then classifies the change as `stock_in`, `stock_out`, or `update`.

## DynamoDB Tables

**`InventoryIQ`** — partition key: `itemID` (UUID string)  
Fields: `name`, `description`, `category`, `quantity`, `price`, `lowStockThreshold`, `userID`, `createdAt`, `updatedAt`

**`Users`** — partition key: `Email` (capital E, string)  
Fields: `passwordHash`, `salt`, `createdAt`

**`InventoryTransactions`** — partition key: `transactionID` (UUID string)  
Fields: `itemID`, `itemName`, `userID`, `changeType` (`create`/`stock_in`/`stock_out`/`update`/`delete`), `quantityBefore`, `quantityAfter`, `quantityDelta`, `notes`, `createdAt`

## Lambda Environment Variables

Python Lambdas read these from `os.environ`:
- `DYNAMODB_TABLE` — defaults to `"InventoryIQ"`
- `TRANSACTIONS_TABLE` — defaults to `"InventoryTransactions"` (used by `AddItem`, `UpdateItem`, `DeleteItem`, `GetTransactions`)
- `SNS_TOPIC_ARN` — ARN for stock alerts
- `SQS_QUEUE_URL` — URL for stock event queue

`Authentication.mjs` reads:
- `USERS_TABLE` — defaults to `"Users"`
- `SNS_TOPIC_ARN` — same as Python Lambdas; used for email subscription on register/login

`LowItemInsight.py` also reads:
- `ALERT_COOLDOWN_HOURS` — defaults to `24`; controls per-user SNS alert frequency

`Proxy.py` reads:
- `API_ENDPOINT` — base URL of the real API Gateway stage (e.g. `https://<id>.execute-api.us-east-1.amazonaws.com/prod`)
- `API_KEY` — the `x-api-key` value injected into forwarded requests; never exposed to the browser

## Lambda Function Patterns

All Python Lambda functions follow a consistent structure with **detailed inline comments** explaining:
1. The data flow (request → processing → response)
2. Key implementation details (pagination, filtering, transaction logging)
3. Edge cases (multi-tenancy checks, Decimal type handling, DynamoDB reserved words)

Key Lambdas:
- **`AddItem.py`** — Creates item, generates UUID, logs "create" transaction
- **`UpdateItem.py`** — Updates item, classifies change type (stock_in/stock_out/update), logs transaction
- **`DeleteItem.py`** — Deletes item, logs "delete" transaction with negative quantity delta
- **`GetAllItems.py`** — Scans user items with pagination (handles 1MB limit)
- **`GetCategories.py`** — Returns unique categories for user, always includes "Uncategorized"
- **`DeleteCategory.py`** — Reassigns items to "Uncategorized" instead of deleting (prevents orphaned items)
- **`GetTransactions.py`** — Returns user's audit log, sorted newest-first, capped at 200 items
- **`LowItemInsight.py`** — Analyzes inventory health (health score, risk assessment, reorder recommendations), publishes SNS alerts + SQS events
- **`DailyAlert.py`** — Scheduled function that generates formatted email report (ASCII art, no HTML) and publishes via SNS
- **`Authentication.mjs`** — Node.js ESM Lambda handling `/auth/register` and `/auth/login`; subscribes user emails to SNS on registration and re-checks subscription on login
- **`Proxy.py`** — Reverse-proxy Lambda that sits in front of all inventory endpoints; reads `API_ENDPOINT` + `API_KEY` from env vars and re-issues the request to the real stage with the key injected. Handles path forwarding via `event['path']`, passes through method and body. **Known limitations:** does not forward query string parameters or handle CORS OPTIONS preflight — ensure the proxy API Gateway resource has `OPTIONS` method with a mock integration returning CORS headers, and that query strings (e.g. `?userID=`) are forwarded explicitly.

## Frontend Architecture

### Script Loading Order
Every protected page loads scripts in this order (critical for dependencies):
1. `config.js` — API endpoint and key configuration
2. `utils.js` — Auth check + nav initialization (must run before page-specific JS)
3. `api.js` — HTTP helpers (`fetch` wrappers, `checkQuota()` error handler)
4. Page-specific `<script>` block — uses all three above

**Auth Flow:**
- `requireAuth()` redirects to `login.html` if no session token in `sessionStorage`
- After login, `Authentication.mjs` returns a UUID token stored in `sessionStorage.userEmail`
- `sessionStorage` persists across page navigation but clears on browser close (security)

### Data Fetching Pattern
Pages use `loadXxx()` function that:
1. Shows "Loading..." state
2. Calls API via `api.js` wrapper
3. Catches errors and displays in-page (red text, no alerts)
4. Renders table with results or error message

Example: `inventory.html` calls `loadInventory()` which:
- Fetches items via `getAllItems()` + categories via `getCategories()` in parallel
- Updates `allItems` and `allCategories` state
- Calls `renderTable()` which generates table HTML from cached data
- Search/filter functions re-render without re-fetching

### Frontend Design System

Tailwind CSS via CDN (no build step). Inter font via Google Fonts CDN. Primary color `#005ab4`. Status badges: emerald = In Stock, yellow = Low Stock, red = Out of Stock.

The app is a multi-page app (MPA) with real browser navigation:
- `login.html` — login + register
- `dashboard.html` — stat cards + read-only inventory table preview (no edit/delete actions)
- `inventory.html` — full inventory table with stock management; Export CSV, Print Report, Manage Categories buttons
- `add-item.html` — add/edit form (edit data passed via `sessionStorage` key `iq_editItem`)
- `insights.html` — AI-driven low-stock analytics
- `transactions.html` — running log of all stock mutations with type filter + search

`utils.js` provides shared helpers: `requireAuth()` (redirects to `login.html` if not authed), `initNav(activePageId)` (highlights active sidebar link matching `data-page` attribute), `handleLogout()`. Every protected page loads `config.js`, `utils.js`, `api.js` in that order. The Tailwind config object is duplicated inline in each page's `<head>` (must precede the CDN `<script src>`).

The sidebar navigation has 4 items: Dashboard, Inventory, Insights, Transactions — present identically in all 5 protected pages.

### Print Report
`inventory.html` has a hidden `#print-section` div populated by `printReport()` before calling `window.print()`. `style.css` contains `@media print` rules that hide the sidebar/header and show only `#print-section`.

### Stock Management & Categories
**inventory.html** provides quick stock adjustments and category management:

**Stock Adjustments (row-level modals on hover):**
- **Plus (+, green)** — opens "Add Stock" modal to increase quantity; logs `stock_in` transaction
- **Minus (−, orange)** — opens "Deduct Stock" modal to decrease quantity; validates against current stock; logs `stock_out` transaction
- Both modals validate positive amounts and update via existing `updateItem()` API (no new backend endpoints)

**Inline Category Dropdown:**
- **Category column in inventory table** displays a `<select>` dropdown for each item
- Changing the dropdown calls `updateItemCategory()`, which PUTs the new category to `UpdateItem.py`
- The local `allItems` cache updates immediately (no table re-render) with a brief checkmark confirmation
- On error, dropdown reverts and shows error message for 3 seconds
- Dropdown options populate from `allCategories` (fetched server-side) + the item's current category

**Manage Categories Modal:**
- **"Manage Categories" button** opens modal to view and modify categories
- Shows existing categories as chips with delete buttons (× icon)
- "Uncategorized" is read-only "(Default)" category — cannot be deleted
- **Create new category:** Input field + "Create" button adds category to `allCategories` in memory
  - New categories immediately appear in all row dropdowns without page reload
  - Categories persist permanently only when assigned to an item (else disappear on refresh)
- **Delete category:** Calls `deleteCategory()` API (DELETE `/categories/{name}?userID=`)
  - `DeleteCategory.py` reassigns all items in that category to "Uncategorized" (no data loss)
  - Shows confirmation dialog: "Moving X items to 'Uncategorized'. Continue?"
  - On success, modal refreshes and table reloads

### Search & Filter Features
- **`inventory.html`** — Search input filters items by name or category (case-insensitive)
  - `applyFilters()` function searches `allItems` and renders matching rows
  - Pagination text updates to show "Showing X of Y assets" (filtered vs total)
  - Refresh button clears search and reloads all items
- **`transactions.html`** — Search + type filter to find specific transactions
  - Search matches transaction item names (case-insensitive)
  - Type dropdown filters by `changeType` (stock_in, stock_out, create, update, delete)
  - Filters work together: search narrows by name, type narrows by change classification

## Error Handling

All frontend pages that fetch data (`dashboard.html`, `inventory.html`, `transactions.html`, `insights.html`) display API errors as red text in the UI instead of silently failing:
- **`api.js`** has a `checkQuota(res)` helper that detects HTTP 429 "API quota exceeded" responses and throws a clear error message
- Each page's data-fetch function wraps `getTransactions()` / `getAllItems()` / `getInsights()` in try-catch
- Errors render inline in tables or panels (e.g., "API quota exceeded — please wait a moment...")

This prevents users from seeing blank/stuck loading states when the API is unavailable or quota is exhausted.

## Common Implementation Patterns

### Adding a New Modal Dialog
1. HTML template: Add hidden `<div id="my-modal" class="hidden fixed inset-0 bg-black/40 z-50 flex items-center justify-center">`
2. Open function: `function openMyModal() { document.getElementById('my-modal').classList.remove('hidden'); }`
3. Close function: `function closeMyModal() { document.getElementById('my-modal').classList.add('hidden'); }`
4. Action function: Call API, then close modal and refresh table: `closeMyModal(); loadInventory();`

### Adding an Inline Edit Control (e.g., category dropdown)
1. In `renderTable()`, generate a `<select>` for each row with `data-item-id="${c.itemID}"` and `onchange="updateField(...)"`
2. Create `updateField(itemID, newValue, selectEl)` function that:
   - Disables the control during the request
   - Calls `updateItem(itemID, { fieldName: newValue, userID })` from `api.js`
   - Updates `allItems` cache on success (avoid re-rendering entire table)
   - Shows success/error feedback inline (checkmark or error text)
3. Return to original value on error and re-enable the control

### State Management
- `allItems` — cached array of inventory items, updated after mutations
- `allCategories` — cached array of user categories, merged from server + local additions
- Filter/search state lives in DOM (input value), not in JS variables
- On page load (via `loadXxx()`), both caches refetch from server; on local mutations, only mutated item updates

## Troubleshooting

**API returns 429 "Limit Exceeded":**
- Your API Gateway usage plan quota has been exhausted. To fix:
  1. AWS Console → **API Gateway** → **Usage Plans** (left sidebar)
  2. Click the usage plan linked to your API key
  3. Click **Edit**
  4. Under **Quota**: uncheck "Enable quota" or raise to 10,000+/day
  5. Click **Save** — takes effect immediately (no redeployment needed)
- All inventory data will appear zero until quota is fixed

**Proxy returns empty data or 400 on GET endpoints:**
- `Proxy.py` does not forward query string parameters by default. Endpoints like `GET /items?userID=` will receive no `userID` and return empty results.
- Fix in `Proxy.py`: append `event.get('queryStringParameters')` to the forwarded URL:
  ```python
  qs = event.get('queryStringParameters') or {}
  qs_string = '&'.join(f"{k}={v}" for k, v in qs.items())
  url = f"{API_ENDPOINT}{path}{'?' + qs_string if qs_string else ''}"
  ```
- Also ensure the proxy API Gateway resource has an `OPTIONS` method with a mock integration that returns CORS headers — otherwise browser preflight requests will fail.

**Lambda Proxy Integration disabled:**
- If a Lambda endpoint returns `{"statusCode": 400, "body": "..."}` in the response body (instead of just the body), you forgot to enable Lambda Proxy Integration in API Gateway
- Fix: API Gateway → Resource → Method → Integration Request → enable "Lambda Proxy Integration" → Save → redeploy
