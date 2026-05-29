# InventoryIQ — Consolidated Agent Intelligence Blueprint

This file serves as the definitive reference guide for **AI Coding Assistants**—including **Claude Code**, **Gemini CLI**, **Codex**, and **Antigravity**—to understand the repository architecture, data models, conventions, and operational constraints.

> [!IMPORTANT]
> **COMPANION FILES:** Always refer to [CLAUDE.md](file:///Users/sidneyordonia/Documents/InventoryIQ/CLAUDE.md) (standard developer guidance) and [GEMINI.md](file:///Users/sidneyordonia/Documents/InventoryIQ/GEMINI.md) (project context overrides) for additional agent-specific context.

---

## 1. Architecture Blueprint & Request Flow

InventoryIQ is a serverless, multi-tenant inventory management system built on AWS. 

```
┌─────────────────────────────────────────────────────────────┐
│                 Static S3 Website (Frontend)                │
│       Plain HTML/JS/CSS  ·  Tailwind CSS (CDN)  ·  Inter    │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS (No API Key exposed)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             API Gateway (Proxy Stage: /prod/proxy/*)        │
└──────────────────────────────┬──────────────────────────────┘
                               │ Forwards Request
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Proxy Lambda (Proxy.py)                     │
│  - Validates session token against "Sessions" (60s cache)   │
│  - Rejects invalid sessions immediately (401 Unauthorized)   │
│  - Injects backend API Key from Secrets Manager (5m cache)   │
│  - Injects tenant identity (x-iq-user) and strips spoofed headers │
└──────────────────────────────┬──────────────────────────────┘
                               │ Forwards with Auth & Key Injected
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               API Gateway (Real Stage: /prod/*)             │
│                 Secured via x-api-key Auth                  │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
┌───────────────────────┐ ┌───────────────┐ ┌───────────────┐
│  Auth Lambda (Node)   │ │  Py Lambdas   │ │   SQS / SNS   │
│  Authentication.mjs   │ │ (CRUD & Ops)  │ │ Alert Topics  │
│  (Bypasses Proxy edge)│ │               │ │ & Event Queue │
└───────────────────────┘ └───────────────┘ └───────────────┘
```

### Edge Proxy Execution Details:
1. **API Key Concealment:** The frontend (`config.js`) only communicates with the `/prod/proxy` endpoint. Downstream API keys are never exposed to the client.
2. **Session Verification:** `Proxy.py` extracts the `X-Session-Token` header, checks it against the `Sessions` DynamoDB table (using a 60-second in-memory cache to prevent duplicate reads), and slides the session expiry (by 8 hours if <4 hours remain).
3. **Identity Injection:** The proxy stamps the validated user email as the `x-iq-user` header and forwards the request to the backend. Any client-provided `x-iq-user` headers are stripped to prevent identity spoofing.

---

## 2. Directory Layout & Core Components

```
├── frontend/               # Static S3 Web assets (HTML, vanilla ESM JS, Vanilla CSS)
├── lambda/                 # Standalone AWS Lambda functions (Python & Node.js ESM)
├── docs/                   # Guided labs, UI design specifications, and artifacts
├── tests/                  # Playwright E2E tests and page objects
├── playwright.config.ts    # E2E test configuration
└── CLAUDE.md / GEMINI.md   # Assistant reference guides
```

### Frontend File Registry (`frontend/`):
*   **`index.html`:** Quick redirect/router shim that sends unauthenticated visitors to `login.html`.
*   **`login.html`:** Dedicated Authentication interface supporting unified signup, sign-in, and SNS alert subscription.
*   **`forgot-password.html` / `reset-password.html`:** Clean workflow for issuing secure, time-limited password recovery emails.
*   **`dashboard.html`:** Responsive home panel displaying critical KPI counts (total products, out-of-stock, low-stock, total value), running audit logs, and status visualizations.
*   **`inventory.html`:** Full asset manager equipped with paginated searches, print report generators, quick stock increments/decrements (+/− modals), category assignments, and CSV exports.
*   **`add-item.html`:** Form for creating assets or editing existing ones (edit payloads are safely parsed from `sessionStorage.iq_editItem`).
*   **`insights.html`:** Advanced inventory analysis showing low-stock products, category weights, and recommended actions.
*   **`forecast.html`:** Predictive stockout planner showing Estimated Daily Burn, Days Until Stockout, and Confidence levels.
*   **`api.js`:** Unified wrapper around the Fetch API providing rate-limiting checks (`checkQuota`), CORS support, and JWT-free header configurations.
*   **`utils.js`:** Shared utilities for checking session permissions (`requireAuth`), logging out, and rendering sidebar menus.
*   **`charts.js`:** Modular scripting to render interactive inventory diagrams.
*   **`style.css`:** Custom styling containing light mode variables, animations, and `@media print` layout modifiers.

### Backend Lambda Registry (`lambda/`):
*   **`Proxy.py`** (Python): Intercepts, authenticates, caches session data, and safely routes browser queries.
*   **`Authentication.mjs`** (Node.js ESM): Manages registration, logins, SES password-reset links, rate-limiting (AuthAttempts), and SNS Topic subscription handling.
*   **`AddItem.py`** (Python): Adds inventory items with automatic UUID assignments and version trackers. Logs events atomically via `transact_write_items`.
*   **`GetAllItems.py`** (Python): Scans the active catalog, handles page splits, and filters out soft-deleted products.
*   **`UpdateItem.py`** (Python): Modifies inventory attributes. Enforces optimistic lock checks against the client-supplied `If-Match` header.
*   **`DeleteItem.py`** (Python): Implements 30-day soft-deletions by writing `deletedAt` and `deletedBy` flags to DB records.
*   **`RestoreItem.py`** (Python): Restores soft-deleted catalog products.
*   **`PurgeDeletedItems.py`** (Python): Routine cleanup script designed to sweep and delete assets that have spent over 30 days in soft-delete.
*   **`GetCategories.py`** (Python): Aggregates unique classification names, always guaranteeing the existence of `"Uncategorized"`.
*   **`DeleteCategory.py`** (Python): Safely deletes category tags, shifting affected items into the default `"Uncategorized"` group to prevent orphaned products.
*   **`GetTransactions.py`** (Python): Gathers the historic user log, ordered chronologically.
*   **`LowItemInsight.py`** (Python): Generates comprehensive reorder insights. Emits SNS alerts + SQS stockout events with a 24-hour alert cooldown per user.
*   **`Forecast.py`** (Python): Generates stockout projections using a Weighted Moving Average (WMA) on `stock_out` logs (30d=50%, 60d=30%, 90d=20%).
*   **`BulkImport.py` / `BulkImportAsync.py`** (Python): Ingests batches of assets via CSV files, utilizing S3 presigned upload URLs.
*   **`BarcodeLookup.py`** (Python): Performs item lookups utilizing barcode records.
*   **`_logging.py`** (Python): Centralized logging utility for standard JSON format metrics.

---

## 3. Database Blueprint (DynamoDB Tables)

The application models its schemas across **7 primary tables** in DynamoDB:

| Table | Partition Key | Sort Key | Global Secondary Indexes (GSI) | TTL Attribute | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`InventoryIQ`** | `itemID` (String) | *None* | `userID-index`<br>(PK: `userID`, SK: `createdAt`) | *None* | Primary store for assets. Attributes: `name`, `description`, `category`, `quantity`, `price` (Decimal), `lowStockThreshold`, `userID` (email), `barcode`, `version`, `createdAt`, `updatedAt`, `deletedAt`, `deletedBy`. |
| **`Users`** | `Email` (String) | *None* | *None* | *None* | Stores accounts. Attributes: `passwordHash` (scrypt), `salt`, `createdAt`. |
| **`Sessions`** | `sessionToken` (String) | *None* | `userID-index`<br>(PK: `userID`, SK: `createdAt`) | `expiresAt` (Unix Secs) | Manages authentication states. Token is an opaque UUID string. |
| **`AuthAttempts`** | `email` (String) | *None* | *None* | `ttl` (Unix Secs) | Tracks failed logins per email for rate-limiting. |
| **`PasswordResets`** | `resetToken` (String) | *None* | *None* | `expiresAt` (Unix Secs) | Tracks single-use password recovery tokens. |
| **`InventoryTransactions`** | `transactionID` (String) | *None* | *None* | *None* | Historic audit trail. Attributes: `itemID`, `itemName`, `userID`, `changeType` (`create`/`stock_in`/`stock_out`/`update`/`delete`), `quantityBefore`, `quantityAfter`, `quantityDelta`, `notes`, `createdAt`. |
| **`IdempotencyKeys`** | `key` (String) | *None* | *None* | `expiresAt` (Unix Secs) | Prevents duplicate requests. Stores `responseBody` and `expiresAt` (24h TTL). |

---

## 4. Key Conventions & Rules (STRICTLY ENFORCED)

### A. General Development Policies
1.  **JWT BANNED:** Never introduce JSON Web Tokens. Authentication is strictly opaque UUID session tokens stored in `Sessions` and managed client-side in `sessionStorage.sessionToken`.
2.  **No Automatic Deployment:** Never attempt to invoke direct AWS Lambda deployment actions automatically. When modifying files in `lambda/`, write the code changes, then explicitly prompt the user with the zip and deployment CLI statements:
    ```bash
    zip function.zip lambda/AddItem.py && aws lambda update-function-code --function-name AddItem --zip-file fileb://function.zip
    ```

### B. Backend Lambda Conventions (Python/Node)
1.  **Multi-User Data Separation:** Inventory items are mapped to owners via `userID` (email). Inside Lambda functions, ALWAYS read the owner's identity from the `x-iq-user` header (injected by the proxy). Never trust client-side user identifiers sent in request bodies or query parameters.
2.  **DynamoDB Decimal Casting:** DynamoDB queries return numeric attributes as `Decimal` objects. Python Lambdas MUST parse and convert all `Decimal` fields to standard `float` or `int` formats prior to executing `json.dumps()` in responses.
3.  **Atomic DB Modifications:** Any backend mutation (`AddItem`, `UpdateItem`, `DeleteItem`) MUST write both the item update and the corresponding `InventoryTransactions` log atomically in a single `TransactWriteItems` call.
4.  **Optimistic Concurrency Controls:** 
    *   Items are created with `version: 1`.
    *   Any update request MUST contain an `If-Match` header representing the client's current version of the item.
    *   `UpdateItem.py` verifies this version matches the DB. On mismatch, it fails fast with `412 Precondition Failed`. On success, it increments the version by 1 and returns the new value as the `ETag` header.
5.  **Soft-Deletions:**
    *   `DeleteItem.py` must never purge records entirely. It marks products as soft-deleted by setting `deletedAt` and `deletedBy` attributes.
    *   `GetAllItems.py` and other inventory reads must actively filter out products that possess a `deletedAt` flag.
    *   Items may be restored within 30 days via `RestoreItem.py` (`POST /items/{id}/restore`).
6.  **Idempotency Protection:** Writes (`AddItem.py`, `BulkImport.py`) must support the `Idempotency-Key` header. If a key has been processed within 24 hours, replay the cached response body directly without re-executing business logic.
7.  **Reserved Words:** `"name"` is a reserved keyword in DynamoDB. Always utilize the expression alias `#nm` when referencing it in query expression structures.

### C. Frontend Script Loading & UI Conventions
1.  **Strict Script Loading Order:** Protected frontend pages must load scripts in this exact sequence to ensure dependency resolution:
    1.  `config.js` — Loads environment configurations (`API_ENDPOINT`, `AUTH_ENDPOINT`).
    2.  `utils.js` — Initializes the navigation sidebar and runs `requireAuth()` validation.
    3.  `api.js` — Provides API communication and helper functions (`getAllItems`, `updateItem`).
    4.  Page-Specific Scripts — Executes page-level hooks and data rendering.
2.  **API Error Handling:** 
    *   Never fail silently. Wrap all API requests inside `try...catch` scopes.
    *   Detect HTTP `429 Too Many Requests` (Quota Exceeded) and HTTP `401 Unauthorized` (Session Expired) using the `checkQuota()` and `check401()` middleware inside `api.js`.
    *   Render all errors directly in the browser layout (using clean, red typography elements) instead of letting loading elements hang indefinitely.
3.  **Design and Theme Consistency:**
    *   **Theme:** Clean, minimalist light-mode layout.
    *   **Font:** Inter (via Google Fonts CDN).
    *   **Colors:** Primary: Blue (`#005ab4`), Secondary: Light Blue (`#e8f0fe`). Sidebar Background: `#f5f6fa`.
    *   **Badges:** Emerald (`#e6f4ea` background, `#137333` text) for *In Stock*, Yellow (`#fef7e0` background, `#b06000` text) for *Low Stock*, Red (`#fce8e6` background, `#c5221f` text) for *Out of Stock*.

---

## 5. Testing & Verification Guide

E2E testing is conducted using Playwright against live AWS endpoints.

### Run Tests:
```bash
npx playwright test                      # Runs all suites
npx playwright test tests/e2e/auth/      # Runs auth suite only
npx playwright test --headed             # Runs with browser visual window
npx playwright show-report               # Displays the HTML report
```

*   **Config File:** [playwright.config.ts](file:///Users/sidneyordonia/Documents/InventoryIQ/playwright.config.ts)
*   **Test Location:** `tests/e2e/` (using Page Object files situated under `tests/pages/`).
*   **Target Scope:** Tests communicate directly with API Gateway and AWS infrastructure. Ensure all endpoints are correctly deployed and that credentials under `notes` match your context before running.
