# InventoryIQ — Agent Reference

Definitive guide for AI coding assistants (Claude Code, Gemini CLI, Codex). `CLAUDE.md` and `GEMINI.md` are redirects to this file.

## Companion Documents — read before you edit

| Document | Read it | What it holds |
|---|---|---|
| **[ARCHITECTURE-ESSENTIALS.md](ARCHITECTURE-ESSENTIALS.md)** | Always — before your first edit, every session | Only the decisions where getting it wrong compiles and passes review, then fails in production |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | When you need structure or exact facts | System diagram, tech stack, full data model, ERD |
| **[PRD.md](PRD.md)** | When the *why* or user-facing behavior matters | Who the product is for, what exists today, what it deliberately is not |

This repo is also indexed by [Graft](graft/) — prefer `graft ask`/`graft callers`/`graft skeleton` over grep for codebase navigation.

---

## 0. OpenWolf Context Protocol

This project uses OpenWolf. Full protocol: [.wolf/OPENWOLF.md](.wolf/OPENWOLF.md). Non-negotiables:

1. Read `.wolf/anatomy.md` before opening files, `.wolf/cerebrum.md` before writing code, `.wolf/buglog.json` before fixing bugs.
2. After significant actions: update `anatomy.md` (file changes), append to `memory.md` (tasks), `cerebrum.md` (corrections/learnings), `buglog.json` (any fix).

---

## 1. Architecture & Request Flow

Serverless multi-tenant inventory system on AWS. Static Netlify frontend (`theinventoryiq.netlify.app`) → API Gateway proxy stage → `Proxy.py` → API Gateway real stage (x-api-key) → Lambdas.

```
Browser (sessionStorage.sessionToken, sent as X-Session-Token)
   │  HTTPS — no API key exposed to client
   ▼
API Gateway  /prod/proxy/{proxy+}
   ▼
Proxy.py
   - Verifies X-Session-Token as HS256 JWT (stdlib hmac — no DB read, no jwt library)
   - Invalid/expired token → 401
   - If X-IQ-Org header present: live membership lookup via _org.get_membership()
     (single GetItem — this is what makes member removal instant). Non-member → 403.
   - Strips client-supplied x-iq-user / x-iq-org / x-iq-role (anti-spoofing),
     injects validated x-iq-user, x-iq-org, x-iq-role
   - Injects backend x-api-key from Secrets Manager (5m cache)
   ▼
API Gateway  /prod/*  (x-api-key required — direct calls without it → 403)
   ▼
Authentication.mjs (Node) · Python CRUD/org Lambdas · SQS/SNS alerts
```

**Auth model (JWT, stateless):**

- `Authentication.mjs` signs an HS256 JWT on login (`sub` = lowercased email). Client stores it in `sessionStorage.sessionToken`.
- Validation is stateless — `Proxy.py` and `Authorizer.mjs` verify the signature with stdlib crypto only. **No external JWT library anywhere; keep it pure `crypto` / `hmac`+`hashlib`.**
- `JWT_SECRET` env var MUST match across `Authentication`, `Proxy`, and `Authorizer` Lambdas or all logins 401.
- The `Sessions` table is now audit-trail + logout cleanup only — never used for token validation.

**Local backend — test locally before any deploy.** Every Lambda change runs on the Mac first; never push an untested handler to AWS.

- Start: `npm run dev:local` (needs Docker running; one-time setup: `npm ci`, `.venv/bin/pip install -r scripts/requirements.txt` and `docker pull floci/floci:2.3.0`). It starts Floci (`floci/floci:2.3.0` container `panindo-floci`, in-memory, fake DynamoDB, SES, SNS, SQS, S3, Secrets Manager) on :4566, `scripts/local_api.py` on :3001 (the real handlers behind `/auth`, `/proxy` and Proxy's `/_backend` target), seeds a test store with `scripts/local_seed.py`, then Vite on :8000 pointed at :3001 via `VITE_API_BASE`. Ports: `LOCAL_FLOCI_PORT`, `LOCAL_API_PORT`, `LOCAL_DEV_PORT`.
- Stop: Ctrl-C stops all four and removes the container. Reseed = restart (Floci keeps nothing).
- Test login: `.local/test-login.json` (gitignored; owner, staff (editor), shared generated password). Never commit it or copy the password anywhere.
- Emails are never sent: the runner prints each SES message Floci captured (read from Floci's `GET /_aws/ses`). Barcode lookups never reach the internet: seeded barcodes answer from `BarcodeCache`, any other code is "not found".
- Gap: `ImportJobs` (used by `BulkImport*.py`) exists only locally; it has no live table yet.
- Rollout rehearsal: `bash scripts/local/rehearse_rollout.sh` mirrors the live Lambdas and `InventoryIQ-API` routes into its own Floci (`panindo-floci-rollout` on :4567, runner on :3101 with `LOCAL_API_GATEWAY=1`, which serves only routes deployed to Floci's `prod` stage), runs every `scripts/rollout_orgs.py` step with `--apply` and, after each, replays main's `ensureOrgContext` (GET /orgs, switch, `X-IQ-Org`), lists and edits items; exits non-zero on 0 items or a failed edit. `--copy-from-live <email>` copies that live store first (read-only scan with your `AWS_PROFILE`; user-run only). `rollout_orgs.py` is dry run by default; a live `--apply` needs `ROLLOUT_LIVE=1`.
- Table layouts in `scripts/local/tables.json` are a copy of the live ones; update it when a live table changes. `npm run dev` and builds still use the live API.

---

## 2. Directory Layout

```
├── frontend/     # Vite + React SPA (shadcn preset b1e6VsioIy). Netlify publishes frontend/dist
├── lambda/       # Standalone Lambdas (Python + Node ESM). python_vendor/ = bundled pip deps
│                 # (sentry_sdk, certifi, urllib3) — include in deploy zips for Lambdas that import them
├── scripts/      # Operational one-shots (migrate_orgs.py)
├── docs/         # PRDs and design artifacts
├── tests/        # Playwright E2E (page objects in tests/pages/) plus tests/unit/python
├── playwright.config.ts
├── vite.config.ts   # SPA. root frontend/, port 8000, appType spa, outDir frontend/dist
└── tsconfig.json
```

### Frontend (`frontend/`)

The runtime is a Vite + React SPA. `frontend/index.html` is the shell (`#root` plus `/src/main.tsx`). Toasts are sonner, mounted by `src/components/ui/sonner.tsx`.

**Routes.** Public: `/login`, `/forgot-password`, `/reset-password`, `/accept`. Signed in, full screen: `/onboarding` (login sends an owner whose store is still "My Inventory" and not onboarded there). Signed in (inside `AppLayout`): `/today`, `/stock`, `/activity`, `/team`, `/insights` (linked from Today, not in the nav). Old routes redirect and keep the query string: `/dashboard` → `/today`, `/inventory` → `/stock`, `/transactions` → `/activity`, `/org` → `/team`, `/add-item` → `/stock?new=1` (or `/stock?item=<id>` when `iq_editItem` holds an existing item). Old `*.html` URLs map through `src/app/legacyHtml.ts`; invite and reset emails still use `/accept.html?token=` and `/reset-password.html?token=`. Netlify 200-rewrites every legacy `*.html` to `/index.html` with `force = true`, so the token stays, and React replace-navigates to the new route.

**Shell.** Desktop: sidebar with brand, org switcher, nav (Today, Stock, Activity, Team) and the account menu at the bottom. Mobile (<768px): top bar (brand + account menu, which also holds the org picker) and a bottom tab bar. Team shows only when `GET /orgs` returned orgs (`useOrgShell().orgsAvailable`); 403/404 from org routes means legacy mode (no `X-IQ-Org`).

**Data.** `src/app/inventory-store.tsx` (`InventoryProvider`, `useInventory`) holds one cache of `GET /items`, plus `GET /transactions` loaded on demand, for every signed-in screen; it reloads on org switch. `src/app/use-stock-actions.ts` is the only write path for items: PUT with `If-Match`, replace the cached row with `response.item`, 412 → toast and reload, toasts with Undo. Item sheets (detail and add) are URL state: `?item=<id>` and `?new=1` on the current route (`src/app/use-sheet-params.ts`), rendered by `src/components/item-sheet/ItemSheetHost.tsx`.

- `src/screens/today/` — greeting + status line, KPI strip (`#stat-total` / `#stat-low` / `#stat-out` / `#stat-value`), Restock next (out + low, most urgent first, Receive dialog and Adjust), recent activity (latest 8 transactions). Never calls `GET /insights`.
- `src/screens/stock/` — `StockScreen` orchestrates `HealthBar` (legend = status filter), `StockToolbar` (search, group by Status/Category, Scan, Count stock, More: categories, import, export, print, deleted), `StockTable` (collapsible groups, selection), `FloatingBar` (bulk actions / count progress), `CountReviewDialog`, `TrashView`, `ImportDialog`, `CategoriesDialog`, `PrintReport`. Filters, grouping, search and the trash view live in the URL (`?status=`, `?group=`, `?q=`, `?view=trash`).
- `src/screens/activity/` — day-grouped feed with filters (All, Stock in, Stock out, Waste and damage, Edits) and search; `?type=` and `?q=` in the URL.
- `src/screens/team/` — seats (members + pending invites against `ORG_SEAT_CAP` default 5), members, invite form (admin/owner only).
- `src/screens/InsightsScreen.tsx` — the only caller of `GET /insights`, on explicit load/refresh.
- `src/screens/LoginScreen.tsx`, `ForgotPasswordScreen.tsx`, `ResetPasswordScreen.tsx`, `AcceptScreen.tsx` — auth. Inputs stay `#login-email` and `#login-password`.
- `src/lib/` — pure helpers with node unit tests in `tests/unit/ts/`: `dashboardStats.ts` (levels, counts, restock queue), `activity.ts` (transaction filters, day groups), `reasons.ts` (adjust reasons → notes), `csv.ts`, `format.ts`.
- `src/config.ts` — `API_ENDPOINT` (`/prod/proxy`) and `AUTH_ENDPOINT` (`/prod/auth`). No API key in the client.
- `src/session.ts` — typed `sessionStorage` keys (`sessionToken`, `userEmail`, `currentOrg`, `currentOrgName`, `currentRole`, `currentCurrency`, `iq_editItem`, `iq_local_logout`).
- `src/api.ts` — the only API client: `checkQuota()` (429), `check401()`, `authHeaders()` (omit `X-IQ-Org` when no org is selected), `If-Match` / 412, idempotency. Throws `ApiError` (with `status`) for item writes and import.
- `src/components/` — `page-header.tsx`, `text-link.ts` (the one inline-link style), `account-menu.tsx`, `status-badge.tsx`, `charts/` (`level-gauge.tsx`, `radial-gauge.tsx`, `stock-bar.tsx`), `barcode-scan-dialog.tsx` (Quagga from jsDelivr, pinned), `confirm-dialog.tsx` (use it instead of `confirm()`), `activity-row.tsx`.
- `src/index.css` — shadcn preset `b1e6VsioIy` theme plus the inventory print sheet.

**Backend limits the UI respects.** Stock change reasons are free text in `notes` ("Used 3", "Waste: 2", "Damaged: 1", "Received 12", "Count fix"); the server derives `stock_in`/`stock_out`/`update`. `GET /transactions` returns at most 200 rows, newest first, no filters, so per-item history is a client-side filter ("recent history"). `price` can arrive as a string; use `priceOf()`. CORS allows GET/POST/PUT/DELETE only (no PATCH) and headers `Content-Type`, `x-api-key`, `X-Session-Token`, `If-Match`, `Idempotency-Key`, `X-IQ-Org`. Import CSV is disabled after its routes answer 403/404. Not built because the backend has no support: suppliers, purchase orders, on-order quantities, snooze, storage locations, usage forecasts, member role changes.

`npm run dev` serves Vite on port 8000 (the live API's CORS origin). `npm run build` typechecks and writes `frontend/dist`. Netlify runs that build and publishes `frontend/dist`.

### Backend (`lambda/`)

- `Proxy.py` — edge auth: JWT verify, org membership check, header injection/stripping.
- `Authorizer.mjs` — API Gateway TOKEN authorizer; validates X-Session-Token JWT, no DB lookup.
- `Authentication.mjs` — register/login/logout, JWT signing, SES password reset, AuthAttempts rate limiting (15-min lockout), SNS subscription, Sentry (`Sentry.wrapHandler`). Lowercases all emails.
- `_org.py` — shared org/RBAC helpers: `get_membership`, `has_role`, `ROLE_RANK`, `list_user_orgs`, seat cap (`ORG_SEAT_CAP`, default 5). Imported by Proxy + org Lambdas.
- `Orgs.py` — org CRUD: list/switch/update (`PUT /orgs/{id}`: name + store fields, owner only)/delete/transfer-owner.
- `OrgMembers.py` — member list, role change, removal.
- `OrgInvites.py` — invite create/revoke/accept. Tokens emailed raw, stored **only as SHA-256 hash** (`inviteTokenHash` PK) — never store or log a raw invite token.
- `_logging.py` — shared `log_json`, `capture_error` (→ Sentry), `response` (CORS envelope), `hash_user`, `plain` (Decimal → JSON int/float), `json_body` (400 `INVALID_JSON`), `number_field` (400 `INVALID_FIELD` + `field`). All Python Lambdas use these; don't hand-roll response dicts.
- `AddItem.py` — create item (UUID, `version: 1`), atomic transaction log.
- `GetAllItems.py` — paginated query (`orgID-index`, fallback `userID-index`), filters soft-deleted.
- `UpdateItem.py` — optimistic-lock update (`If-Match` → 412 on mismatch, new version in `ETag`).
- `DeleteItem.py` / `RestoreItem.py` / `PurgeDeletedItems.py` — 30-day soft-delete lifecycle.
- `GetCategories.py` / `DeleteCategory.py` — category ops; `"Uncategorized"` always exists and absorbs orphans.
- `GetTransactions.py` — chronological audit log.
- `LowItemInsight.py` — reorder insights; SNS alerts + SQS events, 24h cooldown per user.
- `BulkImport.py` / `BulkImportAsync.py` — CSV ingest via S3 presigned URLs.
- `BarcodeLookup.py` — barcode item lookup.
- `CascadeDeleteUser.py` — DynamoDB Streams trigger on `Users` REMOVE; cascades deletion across all user-owned tables.
- `DailyAlert.py` — scheduled daily SNS stock summary.

### Scripts (`scripts/`)

- `migrate_orgs.py` — one-shot backfill: personal org per existing user, stamps `orgID` on their data. **Dry-run by default**; `--apply` writes, `--selftest` runs offline. Idempotent. Prereq: org tables + `orgID-index` GSIs must already exist (it does not create them).

---

## 3. DynamoDB Tables

| Table | PK | SK | GSIs | TTL | Notes |
|---|---|---|---|---|---|
| `InventoryIQ` | `itemID` | — | `userID-index`, `orgID-index` | — | Items: `name`, `category`, `quantity`, `price` (Decimal), `lowStockThreshold`, `userID`, `orgID`, `barcode`, `version`, timestamps, `deletedAt`/`deletedBy` |
| `Users` | `Email` | — | — | — | `passwordHash` (scrypt), `salt`. Streams on — REMOVE triggers `CascadeDeleteUser` |
| `Sessions` | `sessionToken` | — | `userID-index` | `expiresAt` | Audit trail + logout cleanup only. NOT used to validate tokens (JWT is stateless) |
| `AuthAttempts` | `email` | — | — | `ttl` | Failed-login rate limiting, 15-min lockout |
| `PasswordResets` | `resetToken` | — | — | `expiresAt` | Single-use reset tokens |
| `InventoryTransactions` | `transactionID` | — | `orgID-index` | — | Audit trail: `changeType` (`create`/`stock_in`/`stock_out`/`update`/`delete`), before/after/delta quantities |
| `IdempotencyKeys` | `key` | — | — | `expiresAt` | 24h replay cache: stores `responseBody` |
| `Suppliers` | `supplierID` | — | `userID-index`, `orgID-index` | — | Supplier records |
| `Organizations` | `orgID` | — | — | — | `name`, `memberCount`, soft-delete via `deletedAt`; store fields (all optional): `storeType`, `country`, `currency` (ISO 4217, drives money formatting), `onboardedAt` (set once by `PUT /orgs/{id}`) |
| `OrgMembers` | `orgID` | `userID` | `userID-index` | — | `role`, `status` (`active`); the live-lookup table for instant revoke |
| `OrgInvites` | `inviteTokenHash` | — | `orgID-index`, `email-index` | — | SHA-256 of invite token, `role`, invited email |

---

## 4. Conventions (STRICTLY ENFORCED)

### A. General

1. **Auth = stateless HS256 JWT, stdlib only.** Never add a JWT library (`jsonwebtoken`, `PyJWT`, etc.) — signing/verification is pure `crypto` (Node) / `hmac`+`hashlib`+`base64` (Python). `JWT_SECRET` must match on `Authentication`, `Proxy`, and `Authorizer`. Token travels as `X-Session-Token`; client keeps it in `sessionStorage.sessionToken`.
2. **No automatic deployment.** Never invoke AWS deploy commands. Write the code, then give the user the commands:
   ```bash
   zip function.zip lambda/AddItem.py && aws lambda update-function-code --function-name AddItem --zip-file fileb://function.zip
   ```
   Lambdas importing `sentry_sdk` need `python_vendor/` contents in the zip.
3. **Sentry stays.** Node: `@sentry/aws-serverless` + `Sentry.wrapHandler`. Python: `sentry-sdk` via `_logging.capture_error`. `SENTRY_DSN` from env. Never remove instrumentation, never let a handler swallow an exception without `capture_error`.
4. **Unfamiliar feature? Don't write from scratch.** First search GitHub for open-source projects that solve it (same stack where possible), compare two or three approaches, then start — borrowing the proven shape, not the code wholesale, and respecting the ladder above.

### B. Backend

1. **Identity & tenancy:** trust only proxy-injected headers — `x-iq-user` (actor email), `x-iq-org` (data boundary), `x-iq-role`. Never read identity, org, or role from request bodies, query params, or the JWT payload client-side. Role is looked up live per request (`_org.get_membership`) so removal is instant — never cache membership in a token.
2. **RBAC:** `ROLE_RANK = viewer 1 < editor 2 < admin 3 < owner 4`; check with `has_role(have, need)` (rank comparison). Exactly one owner per org. Seat cap via `ORG_SEAT_CAP` (default 5). Enforce on every mutation, not just in UI.
3. **Email normalization:** lowercase every email before any DynamoDB read/write (`.toLowerCase()` / `.lower()`).
4. **Decimal casting:** DynamoDB numerics come back as `Decimal` — convert to `int`/`float` before `json.dumps()`.
5. **Atomic writes:** every mutation writes the item change + `InventoryTransactions` log in one `TransactWriteItems`.
6. **Optimistic locking:** items start at `version: 1`; updates require `If-Match`, mismatch → `412`, success increments version and returns it as `ETag`.
7. **Soft-deletes:** `DeleteItem` sets `deletedAt`/`deletedBy`, never purges. All reads filter `deletedAt`. Restore within 30 days; `PurgeDeletedItems` sweeps after.
8. **Idempotency:** writes honor `Idempotency-Key` — replay cached response within 24h, skip business logic.
9. **Reserved words:** `name` is DynamoDB-reserved — alias as `#nm` in expressions.
10. **Header reads are case-insensitive:** API Gateway lowercases headers, direct invokes may not. Use `_org.header()` or check both cases.
11. **Cascade deletes:** removing a `Users` record fires `CascadeDeleteUser` via Streams across all user-owned tables — never delete user records casually.
12. **Invite tokens:** generate with `secrets.token_urlsafe(32)`, store/lookup only the SHA-256 hash. Raw token appears once, in the invite email.

### C. Frontend

1. **SPA screens:** one shell, `frontend/index.html`, and React routes in `frontend/src/screens/`. Do not add a page HTML file, a Tailwind CDN script, or an inline page script. `onclick` handlers and `window` bindings are gone.
2. **Errors:** wrap API calls in `try/catch`; route 429 through `checkQuota()` and 401 through `check401()`; render errors in the page — never leave a spinner hanging, never fail silently.
3. **Theme:** shadcn preset `b1e6VsioIy` in `frontend/src/index.css` is the source of truth (Tailwind v4 tokens, radius, and fonts). Inter Variable and Roboto Variable load through `@fontsource-variable` and ship with the bundle. Use those tokens (`bg-background`, `text-foreground`, `text-muted-foreground`, and the rest of the `@theme` map). Do not hardcode a second palette.
4. **Feedback:** sonner toasts (`toast()` from `sonner`, rendered by `Toaster` in `frontend/src/components/ui/sonner.tsx`) for every change, with Undo where it is cheap. No `alert()` or `confirm()`: destructive actions use `components/confirm-dialog.tsx`. User text renders as React text, never `dangerouslySetInnerHTML`.
5. **Print:** `@media print` in `frontend/src/index.css`. Stock sets `document.documentElement.dataset.iqPrint = "inventory"` so the report (`screens/stock/PrintReport.tsx`) prints in black on white. The on-screen theme stays on the preset.

---

## 5. Testing

Playwright E2E against live AWS endpoints. Python unit tests live in `tests/unit/python/`.

```bash
npm run dev                              # Vite on http://localhost:8000
npm run build                            # tsc --noEmit && vite build → frontend/dist
npx playwright test                      # all suites; webServer starts Vite
npx playwright test tests/e2e/auth/      # one suite
npm run test:unit                        # node:test over tests/unit/ts (lib helpers)
npx playwright test --headed
npx playwright show-report
```

- Tests hit `/prod/proxy/...` — bare routes like `/prod/categories` return 403 (API key required). Never target bare routes.
- Localhost preview sends `/login` to `/today` unless `sessionStorage.iq_local_logout` is set. `tests/fixtures/auth.ts` sets that flag before page scripts run. A normal browser visit to localhost still uses the preview.
- Page objects: `tests/pages/`. Config: `playwright.config.ts`.
