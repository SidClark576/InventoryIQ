Refer to @CLAUDE.md for more information.

# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.

# InventoryIQ — Project Context

InventoryIQ is a **serverless inventory management application** built on AWS. It provides a multi-user environment for tracking assets, managing categories, and analyzing inventory health with automated alerts.

## Project Overview

*   **Goal:** A visually polished, functional prototype for asset management.
*   **Architecture:** Serverless (AWS Lambda + S3 + DynamoDB + API Gateway).
*   **Access Model:** Multi-tenant isolation based on `userID` (email).
*   **Security:** API Key hiding via a Proxy Lambda, session-based authentication (no JWT), and rate-limiting.

## Technology Stack

*   **Frontend:**
    *   **Styling:** Vanilla CSS + Tailwind CSS (via CDN).
    *   **Logic:** Vanilla JavaScript (ESM where applicable).
    *   **Deployment:** Static assets hosted on AWS S3.
*   **Backend (AWS Lambda):**
    *   **Languages:** Python (Inventory logic) and Node.js (Authentication logic).
    *   **Database:** DynamoDB (multiple tables for Users, Items, Transactions, Sessions).
    *   **Messaging:** SNS (Email alerts) and SQS (Event queue).
    *   **Proxy:** Python Lambda for session validation and API key injection.
*   **Testing:** Playwright for E2E testing.

## Repository Structure

```
frontend/    # S3-deployed static assets (HTML, JS, CSS)
lambda/      # AWS Lambda functions (Python + Node.js ESM)
docs/        # Design artifacts and project documentation
tests/       # Playwright E2E tests and page objects
gan-harness/ # Automated evaluation and smoke tests
```

## Architecture & Data Flow

1.  **Browser** requests go to `Proxy.py` via API Gateway (`/prod/proxy/*`).
2.  **`Proxy.py`** validates the `X-Session-Token` against the `Sessions` DynamoDB table.
3.  On success, it injects the `x-api-key` and forwards the request to the real backend endpoints (`/prod/*`).
4.  **`Authentication.mjs`** handles login/register/reset directly (bypassing the proxy) and manages session tokens.
5.  **Inventory Lambdas** (Python) perform CRUD on DynamoDB and log mutations to `InventoryTransactions`.

## Key Conventions

### Backend (Lambda)
*   **Decimal Handling:** Python Lambdas convert DynamoDB `Decimal` types to `float` before returning JSON.
*   **Transaction Logging:** Every item mutation (`AddItem`, `UpdateItem`, `DeleteItem`) writes an audit record to `InventoryTransactions`.
*   **Optimistic Locking:** `UpdateItem.py` uses an `If-Match` header (versioning) to prevent concurrent write conflicts.
*   **Session Management:** UUID-based opaque tokens with TTL. **JWT is strictly banned.**

### Frontend
*   **Loading Order:** `config.js` → `utils.js` → `api.js` → Page Script.
*   **Auth Check:** `requireAuth()` in `utils.js` redirects unauthenticated users to `login.html`.
*   **State Management:** Local `allItems` and `allCategories` caches are updated after successful API calls to avoid full page reloads.

## Deployment & Development

There is **no local build step** for the application.

### Frontend Deployment
Upload all files in `frontend/` to the designated S3 bucket.
```bash
# Example using AWS CLI
aws s3 sync frontend/ s3://your-inventoryiq-bucket/
```

### Backend Deployment
Each file in `lambda/` is a standalone Lambda. Zip and deploy individually:
```bash
zip function.zip lambda/AddItem.py
aws lambda update-function-code --function-name AddItem --zip-file fileb://function.zip
```

### Testing
Run Playwright E2E tests:
```bash
npx playwright test
```

## Troubleshooting

*   **429 Limit Exceeded:** Check API Gateway Usage Plan quotas.
*   **CORS Issues:** `Proxy.py` handles preflight; ensure `CORS_ORIGIN` env var is set correctly.
*   **Session Expired:** Tokens have an 8-hour TTL (slid by `Proxy.py` if used within 4 hours of expiry).

## DynamoDB Schema Highlights

*   **`InventoryIQ`**: PK `itemID`. Multi-tenant via `userID` field.
*   **`Users`**: PK `Email`. Stores salted `scrypt` hashes.
*   **`Sessions`**: PK `sessionToken`. GSI `userID-index` for bulk invalidation.
*   **`InventoryTransactions`**: PK `transactionID`. Stores `changeType` and quantity deltas.
