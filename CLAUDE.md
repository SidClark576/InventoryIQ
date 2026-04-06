# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InventoryIQ is a **serverless inventory management app** on AWS. There is no local build step — changes are deployed manually to AWS Lambda (Python/Node.js functions) and S3 (frontend).

## Deployment

**Frontend** — upload these files directly to S3:
```
login.html  dashboard.html  inventory.html  add-item.html  insights.html  transactions.html
utils.js    api.js          config.js       style.css
index.html  (redirect shim → login.html)
```

**Backend** — each `.py` file and `index.mjs` is a standalone Lambda function. Deploy individually via the AWS console or CLI:
```bash
zip function.zip AddItem.py && aws lambda update-function-code --function-name AddItem --zip-file fileb://function.zip
```

No package manager, no build tool, no test suite exists in this repo.

**Files NOT deployed:** `notes`, `stitch_design.html`, `update_css.py`. The `notes` file contains live API keys and ARNs — do not modify or commit it.

## Architecture

```
S3 (static HTML/JS frontend)
        │ HTTPS
        ▼
API Gateway (REST, x-api-key auth)
        │
  ┌─────┼──────────────┐
  ▼     ▼              ▼
DynamoDB  SNS Topic   SQS Queue
InventoryIQ  Alerts   StockQueue
Users
InventoryTransactions
```

### API Routes → Lambda mapping
| Method | Path | Lambda |
|--------|------|--------|
| POST | `/auth/register`, `/auth/login` | `index.mjs` (Node.js ESM) |
| GET | `/items` | `GetAllItems.py` |
| POST | `/items` | `AddItem.py` |
| PUT | `/items/{itemID}` | `UpdateItem.py` |
| DELETE | `/items/{itemID}` | `DeleteItem.py` |
| GET | `/insights` | `LowItemInsight.py` |
| GET | `/transactions` | `GetTransactions.py` |

All routes require **Lambda Proxy Integration** enabled in API Gateway.

## Key Conventions

- **Auth:** Passwords hashed with `crypto.scryptSync` (Node.js) + random salt. Login returns a UUID session token stored in `sessionStorage` — there is no server-side token validation after login. All inventory endpoints require `x-api-key` header; auth endpoints do not.
- **Multi-user isolation:** Items are scoped by `userID` (the user's email) stored on each DynamoDB item. `GET /items`, `GET /insights`, and `GET /transactions` require `?userID=` — if omitted, they return an empty result or 400. `userID` is trusted from the client request body (no server-side ownership check on writes).
- **Decimal handling:** DynamoDB returns `Decimal` types — all Python Lambdas convert to `float` before `json.dumps`.
- **CORS:** All Lambdas return `Access-Control-Allow-Origin: *`. The frontend `deleteItem` call appends `?_cb=<timestamp>` with `cache: "no-store"` to avoid stale CORS preflight caches.
- **Low stock logic:** An item is "low stock" when `quantity <= lowStockThreshold`. Out-of-stock is `quantity == 0`. `LowItemInsight.py` publishes SNS + SQS on every GET.
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

`index.mjs` reads:
- `USERS_TABLE` — defaults to `"Users"`

## Frontend Design System

Tailwind CSS via CDN (no build step). Inter font via Google Fonts CDN. Primary color `#005ab4`. Status badges: emerald = In Stock, yellow = Low Stock, red = Out of Stock.

The app is a multi-page app (MPA) with real browser navigation:
- `login.html` — login + register
- `dashboard.html` — stat cards + inventory table preview
- `inventory.html` — full inventory table; Export CSV + Print Report buttons
- `add-item.html` — add/edit form (edit data passed via `sessionStorage` key `iq_editItem`)
- `insights.html` — AI-driven low-stock analytics
- `transactions.html` — running log of all stock mutations with type filter + search

`utils.js` provides shared helpers: `requireAuth()` (redirects to `login.html` if not authed), `initNav(activePageId)` (highlights active sidebar link matching `data-page` attribute), `handleLogout()`. Every protected page loads `config.js`, `utils.js`, `api.js` in that order. The Tailwind config object is duplicated inline in each page's `<head>` (must precede the CDN `<script src>`).

The sidebar navigation has 4 items: Dashboard, Inventory, Insights, Transactions — present identically in all 5 protected pages.

### Print Report
`inventory.html` has a hidden `#print-section` div populated by `printReport()` before calling `window.print()`. `style.css` contains `@media print` rules that hide the sidebar/header and show only `#print-section`.

## Error Handling

All frontend pages that fetch data (`dashboard.html`, `inventory.html`, `transactions.html`, `insights.html`) display API errors as red text in the UI instead of silently failing:
- **`api.js`** has a `checkQuota(res)` helper that detects HTTP 429 "API quota exceeded" responses and throws a clear error message
- Each page's data-fetch function wraps `getTransactions()` / `getAllItems()` / `getInsights()` in try-catch
- Errors render inline in tables or panels (e.g., "API quota exceeded — please wait a moment...")

This prevents users from seeing blank/stuck loading states when the API is unavailable or quota is exhausted.

## Troubleshooting

**API returns 429 "Limit Exceeded":**
- Your API Gateway usage plan quota has been exhausted. To fix:
  1. AWS Console → **API Gateway** → **Usage Plans** (left sidebar)
  2. Click the usage plan linked to your API key
  3. Click **Edit**
  4. Under **Quota**: uncheck "Enable quota" or raise to 10,000+/day
  5. Click **Save** — takes effect immediately (no redeployment needed)
- All inventory data will appear zero until quota is fixed

**Lambda Proxy Integration disabled:**
- If a Lambda endpoint returns `{"statusCode": 400, "body": "..."}` in the response body (instead of just the body), you forgot to enable Lambda Proxy Integration in API Gateway
- Fix: API Gateway → Resource → Method → Integration Request → enable "Lambda Proxy Integration" → Save → redeploy
