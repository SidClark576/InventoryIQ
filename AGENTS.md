# InventoryIQ — Agent Reference

Definitive guide for AI coding assistants (Claude Code, Gemini CLI, Codex). `CLAUDE.md` and `GEMINI.md` are redirects to this file.

---

## 0. OpenWolf Context Protocol

This project uses OpenWolf. Full protocol: [.wolf/OPENWOLF.md](.wolf/OPENWOLF.md). Non-negotiables:

1. Read `.wolf/anatomy.md` before opening files, `.wolf/cerebrum.md` before writing code, `.wolf/buglog.json` before fixing bugs.
2. After significant actions: update `anatomy.md` (file changes), append to `memory.md` (tasks), `cerebrum.md` (corrections/learnings), `buglog.json` (any fix).

---

## 1. Architecture & Request Flow

Serverless multi-tenant inventory system on AWS. Static S3 frontend → API Gateway proxy stage → `Proxy.py` → API Gateway real stage (x-api-key) → Lambdas.

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

---

## 2. Directory Layout

```
├── frontend/     # Static S3 assets: plain HTML, vanilla ESM JS, vanilla CSS
├── lambda/       # Standalone Lambdas (Python + Node ESM). python_vendor/ = bundled pip deps
│                 # (sentry_sdk, certifi, urllib3) — include in deploy zips for Lambdas that import them
├── scripts/      # Operational one-shots (migrate_orgs.py)
├── docs/         # PRDs and design artifacts
├── tests/        # Playwright E2E (page objects in tests/pages/)
└── playwright.config.ts
```

### Frontend (`frontend/`)

- `index.html` — redirect shim to `login.html` for unauthenticated visitors.
- `login.html` — signup, sign-in, SNS alert subscription.
- `forgot-password.html` / `reset-password.html` — time-limited email reset flow.
- `dashboard.html` — KPI counts, audit log, status charts.
- `inventory.html` — paginated search, +/− stock modals, categories, CSV export, print reports.
- `add-item.html` — create/edit form (edit payload from `sessionStorage.iq_editItem`).
- `insights.html` — low-stock analysis and reorder recommendations.
- `forecast.html` — stockout projections (daily burn, days-until-stockout, confidence).
- `suppliers.html` — supplier CRUD, item association.
- `transactions.html` — filtered audit log viewer.
- `api.js` — fetch wrapper: `checkQuota()` (429), `check401()`, CORS headers.
- `utils.js` — `requireAuth()`, logout, sidebar render, toast notifications.
- `charts.js` — chart rendering.
- `config.js` — `API_ENDPOINT`, `AUTH_ENDPOINT`. Must load first on every protected page.
- `style.css` — dark-luxury design system (Section 4.C). `@media print` forces a light report layout.

### Backend (`lambda/`)

- `Proxy.py` — edge auth: JWT verify, org membership check, header injection/stripping.
- `Authorizer.mjs` — API Gateway TOKEN authorizer; validates X-Session-Token JWT, no DB lookup.
- `Authentication.mjs` — register/login/logout, JWT signing, SES password reset, AuthAttempts rate limiting (15-min lockout), SNS subscription, Sentry (`Sentry.wrapHandler`). Lowercases all emails.
- `_org.py` — shared org/RBAC helpers: `get_membership`, `has_role`, `ROLE_RANK`, `list_user_orgs`, seat cap (`ORG_SEAT_CAP`, default 5). Imported by Proxy + org Lambdas.
- `Orgs.py` — org CRUD: list/switch/rename/delete/transfer-owner.
- `OrgMembers.py` — member list, role change, removal.
- `OrgInvites.py` — invite create/revoke/accept. Tokens emailed raw, stored **only as SHA-256 hash** (`inviteTokenHash` PK) — never store or log a raw invite token.
- `_logging.py` — shared `log_json`, `capture_error` (→ Sentry), `response` (CORS envelope), `hash_user`. All Python Lambdas use these; don't hand-roll response dicts.
- `AddItem.py` — create item (UUID, `version: 1`), atomic transaction log.
- `GetAllItems.py` — paginated scan, filters soft-deleted.
- `UpdateItem.py` — optimistic-lock update (`If-Match` → 412 on mismatch, new version in `ETag`).
- `DeleteItem.py` / `RestoreItem.py` / `PurgeDeletedItems.py` — 30-day soft-delete lifecycle.
- `GetCategories.py` / `DeleteCategory.py` — category ops; `"Uncategorized"` always exists and absorbs orphans.
- `GetTransactions.py` — chronological audit log.
- `LowItemInsight.py` — reorder insights; SNS alerts + SQS events, 24h cooldown per user.
- `Forecast.py` — WMA stockout forecast on `stock_out` logs (30d=50%, 60d=30%, 90d=20%).
- `BulkImport.py` / `BulkImportAsync.py` — CSV ingest via S3 presigned URLs.
- `BarcodeLookup.py` — barcode item lookup.
- `Suppliers.py` — supplier CRUD.
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
| `Organizations` | `orgID` | — | — | — | `name`, `memberCount`, soft-delete via `deletedAt` |
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

1. **Script order on protected pages:** `config.js` → `utils.js` → `api.js` → page script. Breaking this breaks auth and API calls.
2. **Errors:** wrap API calls in `try/catch`; route 429 through `checkQuota()` and 401 through `check401()`; render errors in the page — never leave a spinner hanging, never fail silently.
3. **Theme:** dark luxury, dark-only (no toggle). Font: Inter (Google Fonts CDN). Never hardcode palette values — use the CSS variables:
   - Backgrounds `--bg-base: #0a0e1a`, `--bg-surface: #11182b`, `--bg-surface-2: #161f36`, `--bg-surface-3: #1d2942`
   - Borders `--border-subtle: #243352`, `--border-strong: #33476f`
   - Text `--text-primary: #eef2fb`, `--text-secondary: #9fb0d0`, `--text-muted: #5d6f96`
   - Accent `--accent: #005ab4`, `--accent-bright: #3b8df0`, `--gold: #e2b65c`, `--gold-dim: #9c7d3a`
   - Status `--emerald: #34d399` (in stock), `--amber: #fbbf24` (low), `--red: #f87171` (out)
4. **Feedback:** toasts from `utils.js` — no `alert()`, no inline DOM error text for success/info.
5. **Print:** `@media print` overrides dark theme for clean light reports.

---

## 5. Testing

Playwright E2E against live AWS endpoints — no unit test suite; E2E is the coverage strategy here.

```bash
npx playwright test                      # all suites
npx playwright test tests/e2e/auth/      # one suite
npx playwright test --headed
npx playwright show-report
```

- Tests hit `/prod/proxy/...` — bare routes like `/prod/categories` return 403 (API key required). Never target bare routes.
- Page objects: `tests/pages/`. Config: `playwright.config.ts`.
