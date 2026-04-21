# Sprint 4 Evaluation — InventoryIQ
**Date:** 2026-04-21  **Evaluator:** gan-evaluator
**Frontend:** https://main.d5yhjealfqngt.amplifyapp.com
**API:** https://d1g2j27343.execute-api.us-east-1.amazonaws.com/prod

## Test Results (Playwright, 10/10 passed)
| # | Test | Result | Notes |
|---|------|--------|-------|
| 1 | Login → dashboard | PASS | Redirects to dashboard.html, zero console errors |
| 2 | Dashboard stat cards render | PASS | Totals/value/status text all present |
| 3 | Inventory page loads | PASS | Correct empty state "No items found" (item is soft-deleted) |
| 4 | Inventory search filter | PASS | Input filters rows; no-match shows empty row as expected |
| 5 | Manage Categories modal | PASS | Opens, displays Food + Uncategorized chips |
| 6 | Add-item form fields | PASS | Name input + quantity input both detected |
| 7 | Insights page loads | PASS | Health-score text present (health 100, 1 product reported by insights) |
| 8 | Transactions page loads | PASS (test) / BROKEN (UX) | UI shows "2 transactions" but all cells blank — see Blocker B2 |
| 9 | Forgot-password page | PASS | Email input renders |
| 10 | Logout clears session | PASS | Returns to /login.html |

Playwright runtime: 1m 30s, 0 page errors, 0 console errors captured across journeys.

## API Checks
| Endpoint | HTTP | Response | Verdict |
|---|---|---|---|
| POST /auth/login | 200 | `token` + `expiresAt` returned | PASS |
| GET /proxy/items | 200 | `{"items": [], "count": 0}` | PASS (item soft-deleted, expected empty) |
| GET /proxy/categories | 200 | `["Food","Uncategorized"]` | PASS |
| GET /proxy/insights | 200 | summary + recommendations | PASS (keys: summary/outOfStock/lowStock/categoryBreakdown/topReorderPriorities) |
| GET /proxy/transactions | 200 | `["Food","Uncategorized"]` **← wrong payload** | FAIL — returns categories payload, not transactions |
| GET /proxy/items (no X-Session-Token) | 401 | `{"error":"Missing X-Session-Token header"}` | PASS (auth enforced) |

Direct Lambda invoke `aws lambda invoke GetTransactions` returns the correct transactions JSON (4 rows). The fault is in API Gateway wiring, not the Lambda.

**Root cause:** API Gateway resource `/transactions` (resource id `os7che`) GET integration URI is
`arn:...function:GetCategories/invocations` — it points at GetCategories instead of GetTransactions.

## AWS Checks
| Check | Result | Value |
|---|---|---|
| Proxy.Handler | PASS | `Proxy.lambda_handler` |
| Proxy.Timeout | PASS | 29 s |
| Proxy.TracingConfig | PASS | `Mode: Active` (X-Ray on) |
| GetAllItems.Handler | PASS | `GetAllItems.lambda_handler` |
| GetTransactions.Handler | PASS | `GetTransactions.lambda_handler` |
| CloudWatch namespace `InventoryIQ` | PASS | Metrics present: `iq.requests`, `iq.latency_ms`, `iq.errors`, `iq.auth.login_success/fail`, `iq.auth.rate_limited`, `iq.auth.invalid_session` |
| DynamoDB `InventoryIQ` PITR | PASS | `ENABLED` |
| DynamoDB data sanity | PASS | 1 item (soft-deleted), 4 transaction rows |

## Category Scores
| Category | Score /10 | Evidence |
|---|---:|---|
| Auth & Security | 8 | Login 200 + opaque session token; `/proxy/*` rejects missing `X-Session-Token` with 401; session validation + 60 s cache + sliding expiry in Proxy.py; scrypt + salt; rate limiting + PasswordResets table; SES reset flow; X-Ray on. No JWT. Minor: a mis-wired route is an attack-surface smell, though auth is still enforced so no direct security impact. |
| Data Integrity | 7 | Transactions table correctly records create/stock_in/stock_out/update/delete with before/after/delta; PITR enabled; optimistic locking via If-Match forwarded by Proxy. Deduction: users cannot see their transaction history in the UI because the wrong Lambda is wired — integrity preserved, visibility broken. |
| Resilience | 7 | Proxy retries once on 5xx and on network errors; 29 s timeout; module-level caches for sessions (60 s) and API key (5 min, Secrets Manager with env-var fallback); CloudWatch EMF metrics emit per-request latency/errors. Missing: no DLQ evidence on async Lambdas, no alarms observed. |
| Core Functionality | 6 | 10/10 browser journeys load without JS errors, login/logout works, categories CRUD visible, add-item form renders, insights renders health score. But: Transactions page renders 2 "ghost" rows (all cells blank) because the API returns the wrong shape — a user-facing broken feature in a core sidebar page. |
| Domain Logic | 7 | Insights produces healthScore, reorder priorities, category breakdown with correct keys; low-stock/out-of-stock classification intact; soft-delete + transaction audit trail present; category delete reassigns to "Uncategorized". Insights reports `totalProducts:1` while `/items` returns 0 — consistent with soft-delete semantics but the inconsistency should be reconciled. |
| Design/UX | 7 | Clean sidebar, Inter font, consistent blue accent (#005ab4 per spec), solid empty states ("No items found. Showing 0 of 0 assets"), Tailwind-grade spacing. Dashboard/Inventory/Insights feel like a real product. Deductions: Transactions page renders empty dashes instead of detecting broken response (no error banner); pagination shows `1` page even when zero rows; no skeleton loaders on slower routes. |

## Weighted Total
```
Auth 8 × 0.30 = 2.40
Data 7 × 0.20 = 1.40
Res  7 × 0.15 = 1.05
Core 6 × 0.10 = 0.60
Dom  7 × 0.15 = 1.05
UX   7 × 0.10 = 0.70
────────────────────
Total = 7.20 / 10
```

## Verdict: **GO**
- No category ≤ 3
- Auth & Security = 8 (≥ 5)
- Weighted total 7.20 (≥ 6.0)

Sprint 4 post-fix state meets the bar. Proxy handler, Lambda handlers, tracing, EMF metrics, and PITR are verified in prod. One user-visible feature (Transactions list) is broken by an API Gateway wiring error, not a Lambda handler error — fixable in minutes and does not justify a NO-GO, but it is a Sprint 5 prerequisite.

## Blockers (Sprint 5 prerequisites)
- **B1 (must fix):** API Gateway resource `/transactions` GET integration points at `GetCategories`. Re-wire to `GetTransactions` and redeploy the `prod` stage.
  ```bash
  aws apigateway put-integration --rest-api-id d1g2j27343 --resource-id os7che \
    --http-method GET --type AWS_PROXY --integration-http-method POST \
    --uri arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:023202272390:function:GetTransactions/invocations
  aws lambda add-permission --function-name GetTransactions \
    --statement-id apigw-transactions --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn 'arn:aws:execute-api:us-east-1:023202272390:d1g2j27343/*/GET/transactions'
  aws apigateway create-deployment --rest-api-id d1g2j27343 --stage-name prod
  ```
- **B2 (should fix):** `transactions.html` should defensively detect a non-array-of-objects response and render an inline error banner instead of silently rendering dash rows. Guard: `if (!Array.isArray(data) || (data.length && typeof data[0] !== 'object'))` show "Unable to load transactions".
- **B3 (should fix):** Insights `totalProducts` counts soft-deleted items while `/items` excludes them. Pick a single source-of-truth filter (recommend: insights excludes `deletedAt` rows, matching inventory view).
- **B4 (nice to have):** Add CloudWatch alarms on `iq.errors > 0` (5-min window) and on Proxy 5xx rate; metrics exist but no alarms visible.
- **B5 (nice to have):** Audit the integration URIs of every other `/proxy/*` route (`/items`, `/insights`, `/categories`, `/items/{itemID}`, `/items/{itemID}/restore`). If `/transactions` was mis-wired, others may be too.

## Evidence / Artifacts
- Playwright screenshots: `/Users/sidneyordonia/Documents/InventoryIQ/gan-harness/eval-artifacts/01-dashboard.png` through `10-*`
- Key screenshot proving B1/B2: `/Users/sidneyordonia/Documents/InventoryIQ/gan-harness/eval-artifacts/08-transactions.png` — UI shows "2 transactions" with blank cells
- Inventory empty state: `/Users/sidneyordonia/Documents/InventoryIQ/gan-harness/eval-artifacts/03-inventory.png`
- API Gateway misrouting confirmed via `aws apigateway get-integration --rest-api-id d1g2j27343 --resource-id os7che --http-method GET` returning `GetCategories` ARN
- All proxy endpoints verified via curl with `X-Session-Token` header
