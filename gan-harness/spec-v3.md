# InventoryIQ — Product Specification v3

> Generated: 2026-04-13
> Supersedes: `gan-harness/spec-v2.md` (12-week JWT-based plan)
> Audience: GAN Generator agent (implementation) + Evaluator agent (scoring)
> Deployment mode: **MANUAL ONLY** — no auto-deploy, no CI/CD, no GitHub Actions. Every backend change lists explicit `zip` + `aws lambda update-function-code` steps.
> **Auth constraint: NO JWT.** Rationale in §2.

---

## 1. Executive Summary

InventoryIQ is a serverless, multi-tenant inventory SaaS on AWS (Lambda Python/Node.js ESM, DynamoDB, API Gateway, SNS, SQS, S3). v2 planned a JWT-based auth migration; **v3 replaces that with a server-validated opaque session token model backed by DynamoDB** and compresses the roadmap from 12 weeks to **10 weeks**.

**What v3 changes vs v2:**
1. **No JWT anywhere.** All auth moves to DynamoDB-backed opaque session tokens validated server-side in `Proxy.py`. No cryptographic secrets in Lambda env, no token decode in the browser, no `jsonwebtoken` dependency, no HS256/HMAC ceremony on every request.
2. **Simpler session lifecycle.** Login writes a row to `Sessions` table with TTL. Logout deletes it. Expiry is native DynamoDB TTL — not something the frontend interprets.
3. **Proxy.py becomes the single auth chokepoint.** Every proxied request is validated once at the edge; downstream Lambdas trust the server-injected `x-iq-user` header. This matches v2's intent without JWT.
4. **Compressed timeline.** v2's 12 weeks shrinks to 10 because (a) no dual-mode JWT migration period, (b) no frontend token decode/expiry logic, (c) no Secrets Manager rotation dance for a JWT secret (we still move `API_KEY` to Secrets Manager for defense in depth).
5. **Everything else from v2 carries forward unchanged:** ownership checks, GSI migration, idempotency keys, WAF, soft delete, optimistic locking via ETag/If-Match, barcode, CSV import, forecasting, suppliers, POs, multi-location behind a flag, reports, webhooks, CloudFront, power tuning, observability.

### 1.1 JWT exclusion rationale (explicit — the Generator must not reintroduce JWT)
JWT was evaluated and **rejected** for this project because:
- **Secret management pain in serverless.** Rotating an HS256 secret requires a coordinated multi-Lambda redeploy or a version-aware verifier. Opaque tokens rotate per-session for free.
- **Cold-start overhead.** Node's `crypto` is fine but the `jsonwebtoken` package (or a hand-rolled HMAC verifier) still adds bundle weight and one more supply-chain surface. An opaque token is a `GetItem` call that DynamoDB services in ~5ms warm.
- **Revocation.** JWTs cannot be revoked before expiry without a server-side denylist — which is a DynamoDB table anyway. If we're going to maintain a DynamoDB table either way, skip the JWT and just store sessions directly.
- **Frontend complexity.** Decoding `exp` in the browser, refreshing before expiry, handling clock skew — all gone with opaque tokens. The frontend simply sends the token; if the server returns 401, the user re-logs in.
- **Primary source in this project:** `.wolf/cerebrum.md` records the user's earlier decision to avoid JWT after it "caused pain." v3 codifies that.

If the Generator feels tempted to "just add HMAC signing to the opaque token to prevent tampering" — don't. An opaque UUID cannot be tampered with meaningfully because validation is a DB lookup; forged tokens simply miss.

---

## 2. Auth Strategy Decision

### 2.1 Chosen approach: DynamoDB-backed opaque session tokens
- Authentication.mjs on `/auth/login` and `/auth/register`:
  1. Verify credentials (existing scrypt hash check).
  2. Generate `sessionToken = crypto.randomUUID()` (already done today).
  3. **New:** `PutItem` into a new `Sessions` table: `{ sessionToken, userID, createdAt, expiresAt, userAgent, ipHash }` with `expiresAt` as a DynamoDB TTL attribute set to now + 8 hours.
  4. Return `{ sessionToken, userID, expiresAt }` to the client.
- Frontend (`api.js`, `utils.js`):
  - Store `sessionToken` and `userID` in `sessionStorage` (same as today — session-scoped is safer than localStorage for a web app without refresh tokens).
  - Every proxied request sends header `X-Session-Token: <token>`. No `Authorization: Bearer` (that idiom implies JWT; we intentionally use a different header name to make the distinction clear in logs).
  - On any `401` response, clear `sessionStorage` and redirect to `login.html?expired=1`.
- `Proxy.py`:
  1. Short-circuit `/auth/*` — these do not require a session.
  2. Read `X-Session-Token` header. If missing → 401.
  3. `GetItem` on `Sessions` table by `sessionToken`.
  4. If not found, expired (`expiresAt < now`), or record missing → 401.
  5. Extract `userID` from the record. Inject `x-iq-user: <userID>` into the forwarded request to the real `/prod/*` stage. Strip any client-supplied `x-iq-user`.
  6. Cache the validated session in a module-level dict (`_session_cache`) keyed by token with a 60-second local TTL — keeps warm invocations from hammering DynamoDB.
- Downstream Lambdas (AddItem/UpdateItem/DeleteItem/GetAllItems/etc.):
  - Read `userID` from `event.headers['x-iq-user']` (injected by Proxy.py), **never from the request body**. Remove all `userID` body parameters from write paths.
  - For read paths that currently use `?userID=`, also switch to reading from `x-iq-user`; keep the query param parser only as a deprecated fallback for one sprint, then remove.
- Logout: new endpoint `POST /auth/logout` deletes the session row. Called from the header "Log out" button.

### 2.2 Alternatives considered

| Approach | Why rejected |
|---|---|
| **JWT (HS256 / RS256)** | Banned by user; revocation + secret rotation pain in serverless; see §1.1. |
| **AWS Cognito User Pools + API Gateway Authorizer** | Good option on paper (managed, no token verification code). Rejected because: (a) migrating existing users in `Users` table requires running a Cognito import job + forcing password resets — breaks existing accounts; (b) adds a new AWS service to learn and bill; (c) frontend needs the Amplify JS SDK or hand-rolled OAuth flow — both conflict with the no-npm-in-frontend rule; (d) the user's existing scrypt-based password model would be discarded. Revisit in v4 if multi-tenant/SSO becomes a requirement. |
| **Magic link / passwordless** | Good UX but requires SES integration, link token storage, and redirects that break the current session model. Deferred to v4. |
| **API Gateway native API-key per user** | Not designed for end-user auth; API keys are for service-to-service and have no user binding. |
| **Long-lived opaque tokens in sessionStorage without server validation (status quo)** | What we have today. Rejected as the starting point — that's the bug we're fixing. |

### 2.3 Tradeoffs documented

| Concern | Opaque DynamoDB tokens | JWT | Cognito |
|---|---|---|---|
| Revocation | Instant (delete row) | Denylist needed | Instant (admin API) |
| Per-request cost | 1 DynamoDB GetItem (~$0.25 per million, <5ms) | 0 | 0 (within Cognito quota) |
| Secret management | None | HS256 secret everywhere | Managed by AWS |
| Frontend complexity | Send 1 header | Decode/refresh | Amplify SDK or OAuth dance |
| Cold-start impact | Negligible (already using DynamoDB) | +bundle size | +SDK call |
| Works offline | No | Yes (until exp) | No |
| Fits this project | **Yes** | No (banned) | No (migration cost) |

The "works offline" row is the only meaningful JWT advantage and it does not apply — InventoryIQ is an online-only SaaS.

### 2.4 Session table schema
```
Table: Sessions
  PK:  sessionToken (String, UUID)
  TTL attribute: expiresAt (Number, epoch seconds)
  Attributes:
    userID      String   (email, copied from Users.Email)
    createdAt   String   (ISO 8601)
    expiresAt   Number   (epoch seconds; TTL)
    userAgent   String   (optional, truncated to 200 chars)
    ipHash      String   (optional, SHA-256 of source IP — privacy-preserving)
    rotatedFrom String   (optional, sessionToken this one replaced on rotation)
  Billing: on-demand
  PITR: enabled (allows recovery of stolen-session forensics)
```

### 2.5 Session lifecycle rules
- **Lifetime:** 8 hours, sliding — on every successful request, Proxy.py extends `expiresAt` by 8h **iff** current remaining time is < 4h. Prevents every request from being a write.
- **Rotation:** on password change, all sessions for that userID are deleted (scan on GSI `userID-index`, batch-delete).
- **Concurrent sessions:** allowed (multi-device). A per-user cap of 10 active sessions is enforced by a soft check on login (delete oldest if > 10).
- **Logout:** `DELETE` the session row.
- **Failed validation:** Proxy.py logs with `userID_hash` (if derivable) and increments EMF metric `iq.auth.invalid_session`.

---

## 3. Current State Assessment

### 3.1 What works today
(Verified against `.wolf/anatomy.md`, `CLAUDE.md`, `cerebrum.md`.)
- Multi-page vanilla JS frontend (5 protected pages + login). Tailwind CDN. No build.
- `Proxy.py` hides `x-api-key` from browser via server-side injection. `/auth/*` bypasses proxy.
- sessionStorage-based pseudo-auth: UUID generated on login, stored client-side, **never validated server-side** on subsequent requests.
- DynamoDB tables: `InventoryIQ`, `Users`, `InventoryTransactions`. `userID-index` GSI exists on Transactions, used by `GetTransactions.py`.
- SNS email alerts + SQS events for low stock; 24h cooldown via sentinel DynamoDB row.
- Category soft-delete (reassign to "Uncategorized").
- Transaction audit log with 5 change types.
- Manual stock adjustment modals + inline category dropdown.
- CSV export, print report, search/filter on inventory & transactions.

### 3.2 What's broken or weak
| Area | Gap | Severity |
|---|---|---|
| **Auth** | Session token never validated on the server | **CRITICAL** |
| **Auth** | Client-supplied `userID` in request bodies is trusted verbatim — cross-tenant write is trivial | **CRITICAL** |
| **Auth** | No rate limiting on `/auth/login`; brute-force is unconstrained | HIGH |
| **Auth** | No password complexity; no lockout; no forgot-password | HIGH |
| **Auth** | No logout endpoint; sessions never invalidated | MEDIUM |
| DB | `GetAllItems`, `GetCategories`, `LowItemInsight` use `Scan` — O(N across all users) | HIGH |
| DB | No `version` field → last-write-wins on concurrent edits | HIGH |
| DB | Non-atomic item+transaction writes → audit log can diverge from state | HIGH |
| DB | `UpdateItem.py` returns 500 on 404 path due to variable shadowing (line ~56) | HIGH |
| API | `Proxy.py` has URL-encoding gaps and no timeout/retry | MEDIUM |
| API | CORS `*` on every Lambda | MEDIUM |
| Ops | No structured logs, no alarms, no PITR, no DLQs | MEDIUM |
| CDN | Frontend served from S3 website endpoint (no CloudFront, no HTTPS on origin) | MEDIUM |
| Abuse | No WAF in front of API Gateway | MEDIUM |
| Features | No barcode, no CSV import, no forecasting, no suppliers/POs, no multi-location | v3 scope |

### 3.3 Gap vs production SaaS (Zoho / inFlow / Sortly / Cin7)

| Feature | Zoho | inFlow | Sortly | Cin7 | IIQ today | v3 priority | Effort |
|---|---|---|---|---|---|---|---|
| Validated server-side auth | Y | Y | Y | Y | **No** | P0 | M |
| Brute-force protection | Y | Y | Y | Y | No | P0 | S |
| Forgot-password | Y | Y | Y | Y | No | P0 | M |
| Per-tenant data isolation | Y | Y | Y | Y | Weak | P0 | S |
| Optimistic locking | Y | Y | Y | Y | No | P0 | M |
| Idempotency keys | Y (paid) | Y | N | Y | No | P1 | M |
| Barcode scanning | Y | Y | Y | Y | No | P1 | M |
| CSV import | Y | Y | Y | Y | Export only | P1 | M |
| Suppliers / Purchase Orders | Y | Y | N | Y | No | P1 | L |
| Demand forecasting | Y (paid) | Limited | N | Y | No | P2 | M |
| Multi-warehouse | Y | Y | Y | Y | No | P2 | L |
| Reports + PDF | Y | Y | Limited | Y | Basic insights | P2 | M |
| Webhooks | Y | Limited | N | Y | No | P2 | M |
| Audit log | Limited | Y | Y | Y | **Yes** | done | - |
| Low-stock alerts | Y | Y | Y | Y | **Yes (SNS)** | done | - |
| RBAC per user | Y | Y | Y | Y | No | out-of-scope | - |
| Serial/lot tracking | Y (paid) | Y (paid) | N | Y | No | out-of-scope | - |
| Mobile apps | Y | Y | Y | Y | Responsive | out-of-scope | - |

---

## 4. Feature Gap Analysis (single table)

| # | Feature | Exists? | Priority | Effort | Sprint |
|---|---|---|---|---|---|
| 1 | UpdateItem 404-path bugfix (shadowing) | Buggy | P0 | S | 1 |
| 2 | Ownership checks on writes (no cross-tenant writes) | No | P0 | S | 1 |
| 3 | GSI migration for Scan → Query | Partial | P0 | M | 1 |
| 4 | Server-validated opaque session tokens | No | P0 | M | 2 |
| 5 | Password complexity + login rate limiting | No | P0 | S | 2 |
| 6 | Forgot-password (email reset) | No | P0 | M | 2 |
| 7 | Logout endpoint | No | P0 | S | 2 |
| 8 | CORS lockdown + input validation layer | Weak | P0 | M | 2 |
| 9 | Secrets Manager for `API_KEY` | No | P1 | S | 2 |
| 10 | AWS WAF on API Gateway | No | P1 | S | 2 |
| 11 | Idempotency keys on mutations | No | P1 | M | 3 |
| 12 | Optimistic locking via `version` + ETag/If-Match | No | P0 | M | 3 |
| 13 | TransactWriteItems on all mutations (item + txn atomic) | No | P0 | M | 3 |
| 14 | Soft delete + 30d restore + scheduled purge | No | P1 | M | 3 |
| 15 | Proxy URL encoding + timeout + retry | Buggy | P1 | S | 3 |
| 16 | Structured JSON logging (EMF) | No | P1 | S | 4 |
| 17 | CloudWatch alarms + dashboard + PITR | No | P1 | M | 4 |
| 18 | DLQs on SQS + async Lambdas | No | P1 | S | 4 |
| 19 | X-Ray tracing | No | P2 | S | 4 |
| 20 | Synthetic canary | No | P2 | S | 4 |
| 21 | Barcode scanning (QuaggaJS via CDN) | No | P1 | M | 5 |
| 22 | Bulk CSV import (sync + async S3-triggered) | No | P1 | M | 6 |
| 23 | Demand forecasting (weighted moving average) | No | P2 | M | 6 |
| 24 | Suppliers CRUD | No | P1 | M | 7 |
| 25 | Purchase Orders + atomic receive | No | P1 | L | 7 |
| 26 | Multi-warehouse behind feature flag | No | P2 | L | 8 |
| 27 | Reports (valuation, movement, dead stock) + PDF | No | P2 | M | 9 |
| 28 | Webhooks with HMAC-signed payloads | No | P2 | M | 9 |
| 29 | Design tokens + dark mode + empty/loading/error library | Partial | P2 | M | 10 |
| 30 | CloudFront + OAC + Brotli | No | P2 | S | 10 |
| 31 | Lambda Power Tuning + reserved/provisioned concurrency | No | P2 | S | 10 |
| 32 | OpenAPI docs + runbook + status page | No | P2 | S | 10 |

---

## 5. Sprint Breakdown (10 weeks)

Each sprint is **one calendar week**. Every sprint lists: goal, code changes (by filename), manual AWS tasks (separate bucket), acceptance criteria, deployment playbook.

### Sprint 1 — Correctness & Tenancy (foundations)
**Goal:** Fix the UpdateItem bug, enforce per-tenant ownership on every write, migrate remaining Scans to Query.

**Code changes:**
- `lambda/UpdateItem.py`: rename `response = table.get_item(...)` at ~line 56 to `result = table.get_item(...)`; return proper 404 when item missing (not 500).
- `lambda/AddItem.py`, `UpdateItem.py`, `DeleteItem.py`: before mutating, `GetItem`; if record's `userID` ≠ request `userID` (still from body in Sprint 1 — tightened in Sprint 2), return 403.
- `lambda/GetAllItems.py`, `GetCategories.py`, `LowItemInsight.py`: replace `table.scan(FilterExpression=...)` with `table.query(IndexName='userID-index', KeyConditionExpression=Key('userID').eq(userID))`. Paginate with `LastEvaluatedKey`.
- `lambda/GetTransactions.py`: already uses GSI; verify projection is `ALL`.

**Manual AWS tasks:**
1. DynamoDB → `InventoryIQ` table → Indexes → Create GSI `userID-index` (PK=`userID`, projection=ALL, on-demand).
2. Wait for Active status (5–15 min).
3. For each edited Lambda: `zip function.zip lambda/<Name>.py && aws lambda update-function-code --function-name <Name> --zip-file fileb://function.zip`.

**Acceptance:**
- [ ] `PUT /items/<nonexistent>` → 404 (not 500)
- [ ] `PUT /items/<otherUsersItem>` → 403
- [ ] `DELETE /items/<otherUsersItem>` → 403
- [ ] `GET /items?userID=x` returns user's items via Query; CloudWatch shows ConsumedReadCapacityUnits drop
- [ ] Smoke script `gan-harness/tests/sprint1_smoke.sh` (new) passes

### Sprint 2 — Auth Hardening (NO JWT)
**Goal:** Server-validated sessions, brute-force protection, CORS lockdown, WAF, secret relocation.

**Code changes:**
- `lambda/Authentication.mjs`:
  - On `/auth/register`: enforce password regex `^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$`; write session row after creating user.
  - On `/auth/login`: verify scrypt hash; rate-limit via new `AuthAttempts` table (5 fails / 15 min keyed by lowercase email, with TTL); on success write session row to new `Sessions` table; return `{ sessionToken, userID, expiresAt }`.
  - New handler for `POST /auth/logout`: delete session row by token from `X-Session-Token` header.
  - New handler for `POST /auth/forgot-password`: generate reset token (UUID, 1h TTL) into new `PasswordResets` table; SES send email with link `https://<app>/reset-password.html?token=...`. (SES must be out of sandbox or user pre-verifies recipient addresses.)
  - New handler for `POST /auth/reset-password`: verify token, scrypt-hash new password, delete all existing sessions for that user (force re-login everywhere).
- `lambda/Proxy.py`:
  - Read `X-Session-Token`; if `/auth/*` path, skip session validation.
  - `GetItem` on `Sessions` table; reject 401 if missing or `expiresAt < now`.
  - Extract `userID` → inject as `x-iq-user` header on forwarded request. Strip any client-supplied `x-iq-user`.
  - Slide `expiresAt` forward by 8h if remaining < 4h (UpdateItem with ConditionExpression, non-blocking fire-and-forget acceptable).
  - Module-level dict cache `_session_cache` with 60s local TTL.
  - Move `API_KEY` read from env var to Secrets Manager `inventoryiq/api-key`; cache 5 min on warm start.
  - All Lambdas: read `CORS_ORIGIN` env var (comma-separated allow-list); echo `Access-Control-Allow-Origin` only if request `Origin` matches. Default remains `*` only in dev.
- `lambda/AddItem.py`, `UpdateItem.py`, `DeleteItem.py`, `GetAllItems.py`, etc.: read `userID` from `event['headers']['x-iq-user']`, fall back to query/body only if header missing (Sprint 3 removes the fallback).
- `frontend/api.js`: add `X-Session-Token: <sessionStorage.sessionToken>` to every proxied request; on 401 response clear sessionStorage and redirect to `login.html?expired=1`.
- `frontend/login.html`: store `sessionToken` + `userID` on login success. New `reset-password.html` + `forgot-password.html` pages.
- `frontend/utils.js`: `handleLogout()` calls `POST /auth/logout` before clearing sessionStorage.

**Manual AWS tasks:**
1. DynamoDB → create `Sessions` (PK=`sessionToken`, TTL=`expiresAt`, on-demand, PITR on, GSI `userID-index` for bulk-invalidate on password reset).
2. DynamoDB → create `AuthAttempts` (PK=`email`, TTL=`ttl`).
3. DynamoDB → create `PasswordResets` (PK=`resetToken`, TTL=`expiresAt`).
4. SES → verify sender domain; move out of sandbox OR verify every test recipient.
5. Secrets Manager → create `inventoryiq/api-key` with current `x-api-key` value; grant `Proxy` Lambda role `secretsmanager:GetSecretValue`.
6. WAF & Shield → create WebACL `inventoryiq-prod` with: `AWSManagedRulesCommonRuleSet`, `AWSManagedRulesKnownBadInputsRuleSet`, rate-based rule (1000 req / 5 min / IP). Attach to API Gateway stage `prod`. **Start in Count mode for 48h, promote to Block.**
7. API Gateway → add routes `POST /auth/logout`, `POST /auth/forgot-password`, `POST /auth/reset-password`; deploy stage.
8. Zip + update Authentication.mjs and Proxy.py; zip + update each modified Lambda.
9. S3 sync frontend.

**Acceptance:**
- [ ] Register with weak password → 400 with field error
- [ ] 6 failed logins in 15 min → 429 with `Retry-After` header
- [ ] Valid login returns `sessionToken`; `GET /items` works with that token in `X-Session-Token`
- [ ] Deleting the session row (manual DynamoDB delete) → next request returns 401
- [ ] `POST /auth/logout` → subsequent calls with that token 401
- [ ] Forgot-password email arrives within 60s; reset link sets new password; all prior sessions invalidated
- [ ] WAF console shows non-zero sample requests; synthetic SQLi in query string blocked once promoted to Block
- [ ] CORS: request from unlisted origin → preflight fails
- [ ] `API_KEY` rotated in Secrets Manager → Proxy picks up new value within 5 min with zero Lambda redeploys
- [ ] **Verify: no "jwt", "jsonwebtoken", "HS256", or "Bearer" token strings anywhere in the Lambda code** (grep is the evaluator's friend)

### Sprint 3 — Data Integrity
**Goal:** Every mutation is atomic and version-safe; deletes are reversible.

**Code changes:**
- `lambda/_common/` (Lambda Layer `iq-common` — see §6.3):
  - `_validation.py` (name 1–200, price≥0, quantity≥0 int, threshold≥0, description≤2000)
  - `_response.py` (ok/err helpers with env-driven CORS)
  - `_auth.py` (`get_user_from_event(event)` reads `x-iq-user`; no JWT decode anywhere)
  - `_idempotency.py` (decorator: reads `Idempotency-Key` header; short-circuits on replay using `IdempotencyKeys` table)
  - `_logging.py` (EMF-format JSON)
- `lambda/AddItem.py`, `UpdateItem.py`, `DeleteItem.py`: use `dynamodb.meta.client.transact_write_items([...])` to write item mutation + transaction log atomically. On `TransactionCanceledException`, return 409.
- `lambda/UpdateItem.py`: add `version` field. Require `If-Match: <version>` header. Return `412 Precondition Failed` on mismatch; `428 Precondition Required` if header absent. Response includes `ETag: <newVersion>`.
- `lambda/DeleteItem.py`: change to soft delete — set `deletedAt`, `deletedBy`, leave row in DB.
- `lambda/GetAllItems.py`: add `FilterExpression=attribute_not_exists(deletedAt)`.
- New `lambda/RestoreItem.py`: `POST /items/{id}/restore`; removes `deletedAt`.
- New `lambda/PurgeDeletedItems.py`: EventBridge `rate(1 day)`; hard-deletes items where `deletedAt < now - 30d`.
- `lambda/Proxy.py`: percent-encode query params via `urllib.parse.quote(..., safe='=&')` on re-issue; 10s timeout; 1 retry on 5xx (not on 4xx).
- Remove all Sprint-1-era body/query-string `userID` fallbacks; Lambdas now read exclusively from `x-iq-user`.

**Manual AWS tasks:**
1. Build and publish Lambda Layer `iq-common`: `cd layer && pip install -t python/ (nothing external needed) && zip -r layer.zip python && aws lambda publish-layer-version --layer-name iq-common --zip-file fileb://layer.zip`.
2. Attach layer to every Python Lambda: `aws lambda update-function-configuration --function-name <X> --layers <layer-arn>` (script `scripts/update_all_layers.sh`).
3. DynamoDB → create `IdempotencyKeys` (PK=`key`, TTL=`expiresAt`).
4. DynamoDB → run `scripts/backfill_schema_version.py` locally with `AWS_PROFILE` set to add `version=1, schemaVersion=1` to every existing item.
5. EventBridge → create rule `inventoryiq-purge-deleted` `rate(1 day)` → target `PurgeDeletedItems`.
6. API Gateway → add `POST /items/{itemID}/restore`; deploy.

**Acceptance:**
- [ ] Two concurrent `PUT` with same `version` → second returns 412
- [ ] `PUT` without `If-Match` → 428
- [ ] Same `Idempotency-Key` POSTed twice within 24h → identical body, only one item created
- [ ] Induced failure between item write and transaction write → neither persists (transaction rolled back)
- [ ] `DELETE /items/<id>` → item has `deletedAt`, hidden from `GET /items`
- [ ] `POST /items/<id>/restore` within 30d → item visible again
- [ ] After 30d + 1 day → purge Lambda fires, item gone

### Sprint 4 — Observability & Resilience
**Goal:** When something breaks, we know immediately and nothing is lost.

**Code changes:**
- All Python Lambdas: switch to `_logging.log_json(event, level='INFO', function=..., latency_ms=..., userID_hash=sha256(userID)[:12])`. Emit EMF custom metrics `iq.requests`, `iq.errors`, `iq.latency_ms` with dims `{function}`.
- Authentication.mjs: same structured logs; emit `iq.auth.login_success`, `iq.auth.login_fail`, `iq.auth.invalid_session`, `iq.auth.rate_limited`.

**Manual AWS tasks:**
1. DynamoDB → every table → Continuous backups → enable PITR.
2. SQS → create `StockQueueDLQ` and `LambdaDLQ`. Set `StockQueue` redrive maxReceiveCount=3 → DLQ.
3. Lambda → each async-invoked function (DailyAlert, PurgeDeletedItems, LowItemInsight SNS path) → Configuration → Async invocation → DLQ = `LambdaDLQ`.
4. Lambda → each function → Monitoring → Active tracing ON (X-Ray).
5. API Gateway → stage `prod` → Logs/Tracing → X-Ray ON.
6. CloudWatch → Synthetics → create canary `iq-auth-canary` (Node runtime) that hits `/auth/login` with a dedicated canary account + `GET /items`; cadence 5 min; alarm on 2/3 failures → SNS to user email.
7. CloudWatch → Alarms: Lambda errors > 1% over 5 min per function; Lambda duration p95 > 3s; DynamoDB throttled requests > 0; DLQ ApproximateNumberOfMessagesVisible > 0.
8. CloudWatch → Dashboard `inventoryiq-prod`: request volume, error rate, p95 latency per function, DLQ depth, session table size.
9. DynamoDB → Contributor Insights enabled on `InventoryIQ` and `InventoryTransactions`.

**Acceptance:**
- [ ] X-Ray service map shows API GW → Proxy → downstream Lambda → DynamoDB
- [ ] Forcing a Lambda to throw 3× → message in `LambdaDLQ`
- [ ] Canary green for 24h; a forced failure pages via SNS
- [ ] EMF metric `iq.latency_ms` appears under CloudWatch → Metrics → Custom
- [ ] Dashboard loads and shows real data

### Sprint 5 — Barcode Scanning
**Goal:** Scan barcodes with phone camera on `add-item.html` and `inventory.html`.

**Code changes:**
- `frontend/add-item.html`, `inventory.html`: integrate QuaggaJS via CDN `https://cdn.jsdelivr.net/npm/@ericblade/quagga2/dist/quagga.min.js`; camera-picker modal; fallback to manual entry and image-upload decode if `getUserMedia` denied.
- New `lambda/BarcodeLookup.py`: `GET /barcode/{code}`; try DynamoDB cache (30d TTL) → Open Food Facts → UPC Item DB; populate cache on miss.
- `AddItem.py`, `UpdateItem.py`: add optional `barcode` field (indexed via new GSI `barcode-userID-index`).

**Manual AWS tasks:**
1. DynamoDB → create `BarcodeCache` (PK=`code`, TTL=`ttl`).
2. DynamoDB → `InventoryIQ` → GSI `barcode-userID-index` (PK=`barcode`, SK=`userID`, projection=KEYS_ONLY).
3. Deploy `BarcodeLookup.py`.

**Acceptance:**
- [ ] Scanning a real product barcode auto-fills name + category in add-item form
- [ ] Second scan of same code hits cache (no external API call)
- [ ] Denied camera permission shows manual/file-upload fallback

### Sprint 6 — Bulk CSV Import + Demand Forecasting
**Goal:** Two high-leverage productivity features.

**Code changes:**
- New `lambda/BulkImport.py`: inline sync for ≤100 rows.
- New `lambda/BulkImportAsync.py`: S3 `ObjectCreated` trigger on `inventoryiq-imports/` prefix; chunks into TransactWriteItems batches; writes progress to new `ImportJobs` table; frontend polls `GET /import/{jobId}`.
- Frontend: drag-and-drop modal on `inventory.html`; per-row error list; downloadable template `frontend/import-template.csv`.
- New `lambda/Forecast.py`: computes weighted moving average of `stock_out` transactions per item over last 30/60/90 days; returns `{itemID, dailyBurn, daysUntilStockout, confidence, suggestedThreshold, method: 'WMA', sampleSize, windowDays, lastUpdated}`.
- New `frontend/forecast.html` page; sidebar entry.

**Manual AWS tasks:**
1. S3 → create bucket `inventoryiq-imports` with lifecycle rule (delete after 7 days).
2. DynamoDB → create `ImportJobs` (PK=`jobId`, TTL=`ttl`).
3. Deploy `BulkImport.py`, `BulkImportAsync.py`, `Forecast.py`; wire S3 trigger.
4. API Gateway → add `POST /items/import`, `GET /import/{jobId}`, `GET /forecast`; deploy.

**Acceptance:**
- [ ] 50-row CSV imports inline; errors listed per row
- [ ] 800-row CSV uploads to S3, progresses asynchronously, completes within 2 min
- [ ] `GET /forecast` returns plausible burn rates for items with ≥ 7 stock_out events
- [ ] Forecast page renders urgency cards (red/yellow/green by `daysUntilStockout`)

### Sprint 7 — Suppliers & Purchase Orders
**Goal:** Close the biggest domain-feature gap vs Zoho/inFlow.

**Data model:**
- `Suppliers` table: PK=`supplierID`, GSI `userID-index`, attrs: `userID, name, contactEmail, phone, address, leadTimeDays, notes, createdAt`.
- `PurchaseOrders` table: PK=`poID`, GSI `userID-index`, attrs: `userID, supplierID, status (draft/sent/partial/received/closed), createdAt, sentAt, expectedAt, receivedAt, lineItems[], totalCost, version`.
- Items gain `supplierID` optional FK.

**Code changes:**
- New Lambdas: `CreateSupplier.py`, `GetSuppliers.py`, `UpdateSupplier.py`, `DeleteSupplier.py`, `CreatePO.py`, `GetPOs.py`, `UpdatePO.py`, `ReceivePO.py` (atomic across up to 25 line items using TransactWriteItems; logs one stock_in transaction per line with `notes: "PO <poID>"`).
- New frontend: `suppliers.html`, `purchase-orders.html`. Inventory row action "Create PO" prefilled with forecast-suggested reorder quantity.

**Manual AWS tasks:**
1. Create `Suppliers` + `PurchaseOrders` tables with GSIs.
2. API Gateway: 8 new routes, Lambda Proxy Integration, redeploy stage.
3. Deploy 8 new Lambdas.

**Acceptance:**
- [ ] Full supplier CRUD
- [ ] Create PO from inventory row → line prefilled with `suggestedThreshold × 2`
- [ ] Full PO receipt increments all line items atomically; transactions logged with PO ref
- [ ] Partial receipt updates status to `partial`; remaining qty tracked
- [ ] Deleting supplier with open PO → 409 listing blocking PO IDs

### Sprint 8 — Multi-Warehouse (feature-flagged)
**Goal:** Optional multi-location support; off by default; zero regression for existing users.

**Data model:**
- `Locations` table: PK=`locationID`, GSI `userID-index`.
- `ItemStock` table: PK=`itemID`, SK=`locationID`, attrs: `quantity, lowStockThreshold (optional override), updatedAt, version`.
- `Users` table gains `features.multiLocation: bool`.

**Code changes:**
- New Lambdas: `CreateLocation.py`, `GetLocations.py`, `UpdateLocation.py`, `DeleteLocation.py`, `Transfer.py` (atomic two-entry transaction log + two ItemStock updates).
- Modify `GetAllItems.py`, `AddItem.py`, `UpdateItem.py`, `LowItemInsight.py` to join ItemStock when feature flag is on; otherwise preserve existing single-quantity behavior.
- New `frontend/locations.html`; inventory table location filter; item detail per-location breakdown with transfer button.
- `scripts/migrate_to_locations.py`: dry-run mode; for each existing item, create one ItemStock row at user's default location with current quantity.

**Manual AWS tasks:**
1. Create `Locations` + `ItemStock` tables.
2. PITR snapshot before migration.
3. Run migration script with `--dry-run` then for real.
4. Deploy new Lambdas + modified Lambdas.

**Acceptance:**
- [ ] Flag off → UI identical to Sprint 7; full regression suite green
- [ ] Flag on → location selector appears; default location created with all existing stock
- [ ] Transfer 5 units A→B → two transaction rows, totals conserved
- [ ] Sum of per-location stock equals aggregate item quantity reported in dashboard

### Sprint 9 — Reports + Webhooks
**Goal:** Customer-expected reporting + programmable integrations.

**Code changes:**
- New Lambdas: `ReportValuation.py`, `ReportMovement.py`, `ReportDeadStock.py`, `ReportPDF.py` (reportlab via Lambda Layer), `WebhookRegister.py`, `WebhookDispatcher.py` (SNS-triggered, HMAC-SHA256-signs payloads with per-webhook secret, auto-disables after 5 consecutive delivery failures, emails the user).
- New frontend: `reports.html` with date range, category + supplier filters, CSV/PDF export. `settings.html` with webhook CRUD + last-50 delivery log.
- Every mutating Lambda publishes to SNS topic `inventoryiq-events` on success.

**Manual AWS tasks:**
1. Build reportlab Lambda Layer: `cd layer-reportlab && pip install -t python/ reportlab && zip -r layer.zip python && aws lambda publish-layer-version --layer-name iq-reportlab --zip-file fileb://layer.zip`.
2. SNS → create topic `inventoryiq-events`.
3. Grant every mutating Lambda `sns:Publish`.
4. DynamoDB → `Webhooks` (PK=`webhookID`, GSI `userID-index`) + `WebhookDeliveries` (PK=`deliveryID`, GSI `webhookID-createdAt-index`, TTL=`ttl`).
5. Subscribe `WebhookDispatcher` to `inventoryiq-events`; configure DLQ.

**Acceptance:**
- [ ] Register webhook pointing at `https://webhook.site/<id>` → creating an item POSTs signed payload within 10s
- [ ] `X-IQ-Signature: sha256=<hex>` header validates against documented secret
- [ ] Webhook URL returning 500 five times → auto-disabled; user emailed
- [ ] Reports page renders valuation in < 2s at 1000 items
- [ ] PDF opens in Preview / Acrobat

### Sprint 10 — Polish, Performance, Launch
**Goal:** Design system, CDN, power tuning, pre-launch gates.

**Code changes:**
- `frontend/design-tokens.css` (CSS custom properties: colors, spacing scale 4/8/12/16/24/32, radii, shadows, font stacks).
- Dark-mode toggle in header (CSS `:root[data-theme="dark"]` overrides; preference in localStorage).
- Density toggle (comfortable default, compact rows 32px).
- Empty/loading/error state components duplicated across `inventory.html`, `transactions.html`, `insights.html`, `forecast.html`, `reports.html`, `suppliers.html`, `purchase-orders.html`.
- `frontend/status.html` reads a JSON heartbeat written by the canary.
- `docs/openapi.yaml`, `docs/user-guide.md`, `docs/runbook.md`.

**Manual AWS tasks:**
1. Run AWS Lambda Power Tuning state machine against each Python Lambda; set recommended memory (512–1024 MB typical).
2. Provisioned concurrency: `Proxy` (1–2), `GetAllItems` (1).
3. CloudFront + Origin Access Control in front of the S3 frontend bucket; enable Brotli; set `PriceClass_100`; cache static assets long-term with manual hash suffixes.
4. AWS Budgets: alerts at $5 / $20 / $50 to user email.
5. OWASP ZAP baseline scan against production URL; triage to 0 High, ≤ 3 Medium with documented mitigations.
6. PITR restore drill: restore a table to a new name, spot-check 10 rows.

**Acceptance:**
- [ ] p95 `GET /items` ≤ 400 ms from US-East
- [ ] Cold-start rate on `Proxy` < 2% over 1h synthetic load
- [ ] Projected cost at 100 MAU ≤ $15/month (documented)
- [ ] ZAP baseline: 0 High, ≤ 3 Medium (documented)
- [ ] PITR-restored row matches byte-for-byte
- [ ] Lighthouse Accessibility ≥ 95 on every page
- [ ] `docs/runbook.md` covers: token leak, DynamoDB throttling, WAF false positive, Lambda rollback, SES bounce

---

## 6. Technical Architecture

### 6.1 Target architecture (ASCII)
```
                                       ┌──────────────┐
     Browser ── HTTPS ── CloudFront ───┤ S3 (static)  │
                     │                 └──────────────┘
                     │  X-Session-Token: <uuid>
                     ▼
                API Gateway (/prod/proxy/*)     ── WAF (managed rules + rate)
                     │
                     ▼
                  Proxy.py
                  ─ GET Sessions[token] (module-cache 60s)
                  ─ reject 401 if missing/expired
                  ─ slide expiresAt if remaining < 4h
                  ─ inject x-iq-user header
                  ─ inject x-api-key from Secrets Manager (5min cache)
                     │
                     ▼
                API Gateway (/prod/*)           ── WAF
                     │
      ┌──────────────┼─────────────┬──────────────┐
      ▼              ▼             ▼              ▼
  Inventory     Auth Lambda    Reports /      Webhooks
  Lambdas       (login,        PDF Lambda     Dispatcher
  (TransactWrite registration, (reportlab)    (HMAC sign)
   for item+txn) forgot-pw,                       │
                 logout)                          ▼
      │              │             │         SNS inventoryiq-events
      │              │             │             │ ──► SQS DLQ
      ▼              ▼             ▼             ▼
  DynamoDB       DynamoDB      DynamoDB      3rd-party webhook URLs
  InventoryIQ    Users         (aggregates)
  InventoryTxns  Sessions (TTL)
  Suppliers      AuthAttempts
  PurchaseOrders PasswordResets
  Locations      IdempotencyKeys
  ItemStock      Webhooks
  BarcodeCache   WebhookDeliveries
  ImportJobs
  (no JWT secret — anywhere)
```

### 6.2 DynamoDB table summary

| Table | PK | SK | GSI | TTL | Purpose |
|---|---|---|---|---|---|
| InventoryIQ | itemID | — | userID-index, barcode-userID-index | — | Items |
| InventoryTransactions | transactionID | — | userID-createdAt-index | — | Audit log |
| Users | Email | — | — | — | Accounts |
| **Sessions** | sessionToken | — | userID-index | expiresAt | Opaque session tokens |
| AuthAttempts | email | — | — | ttl | Brute-force counter |
| PasswordResets | resetToken | — | — | expiresAt | Forgot-password tokens |
| IdempotencyKeys | key | — | — | expiresAt | Replay suppression |
| Suppliers | supplierID | — | userID-index | — | Sprint 7 |
| PurchaseOrders | poID | — | userID-index | — | Sprint 7 |
| Locations | locationID | — | userID-index | — | Sprint 8 |
| ItemStock | itemID | locationID | — | — | Sprint 8 |
| BarcodeCache | code | — | — | ttl | Sprint 5 |
| ImportJobs | jobId | — | — | ttl | Sprint 6 |
| Webhooks | webhookID | — | userID-index | — | Sprint 9 |
| WebhookDeliveries | deliveryID | — | webhookID-createdAt-index | ttl | Sprint 9 |

### 6.3 Shared Lambda Layer `iq-common`
- `_auth.py`: `get_user_from_event(event)` returns `event['headers']['x-iq-user']` — **no JWT decode, no token verification happens here; that is Proxy.py's job**.
- `_validation.py`, `_response.py`, `_idempotency.py`, `_logging.py` as described in Sprint 3.

### 6.4 Error envelope (all Lambdas)
```json
{ "error": { "code": "VALIDATION_FAILED", "message": "quantity must be >= 0", "field": "quantity", "requestId": "..." } }
```
Codes: `VALIDATION_FAILED`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `PRECONDITION_FAILED`, `RATE_LIMITED`, `INTERNAL`.

---

## 7. Evaluation Rubric (Generator-facing)

Final score = weighted sum (0–10 each). Same file written separately to `gan-harness/eval-rubric-v3.md` for Evaluator consumption.

| # | Category | Weight |
|---|---|---|
| 1 | **Auth & Security (NO JWT)** | 0.30 |
| 2 | Data Integrity | 0.20 |
| 3 | Resilience & Observability | 0.15 |
| 4 | Core Features (barcode, CSV, forecast) | 0.10 |
| 5 | Domain Features (suppliers/PO/locations/reports/webhooks) | 0.15 |
| 6 | Design & UX Polish | 0.10 |

### 7.1 Auth & Security (0.30)
| Score | Criteria |
|---|---|
| 0–2 | sessionStorage-only trust; any JWT reference present → automatic score cap at 2 |
| 3–4 | Session validation exists but JWT-shaped (Authorization: Bearer, `jwt.verify`, HS256 constants) → cap at 4 |
| 5–6 | Opaque token + Sessions table + Proxy.py validation + CORS lockdown + password complexity |
| 7–8 | + login rate limiting + forgot-password + logout + WAF in Block mode + Secrets Manager for API key |
| 9–10 | + sliding expiry + per-user session cap + bulk session invalidation on password reset + canary alert on auth failures |

**Auto-fail gate:** any file in `lambda/` containing the string `jwt`, `jsonwebtoken`, `HS256`, `RS256`, `verify_jwt`, or `Authorization: Bearer` outside a comment explaining why it's banned → category score = 0.

### 7.2 Data Integrity (0.20)
| Score | Criteria |
|---|---|
| 0–2 | No atomicity, no versioning, hard deletes |
| 5–6 | TransactWriteItems on all mutations, `version` field, If-Match/ETag, idempotency keys |
| 9–10 | + soft delete with 30d restore + scheduled hard-purge + backfill script proves existing items migrated |

### 7.3 Resilience & Observability (0.15)
| Score | Criteria |
|---|---|
| 5–6 | Structured JSON/EMF logs, CloudWatch alarms, PITR, DLQ on SQS |
| 9–10 | + X-Ray end-to-end + synthetic canary + Contributor Insights + dashboard + runbook |

### 7.4 Core Features (0.10)
| Score | Criteria |
|---|---|
| 5–6 | Barcode scanning + CSV import (sync) + forecast endpoint |
| 9–10 | + async large-import pipeline + forecast explainability payload + reorder threshold auto-suggest |

### 7.5 Domain Features (0.15)
| Score | Criteria |
|---|---|
| 5–6 | Supplier CRUD + PO lifecycle including atomic receive |
| 7–8 | + reports (valuation, movement, dead stock) + PDF |
| 9–10 | + webhooks (HMAC, auto-disable) + multi-location behind flag with transfer flow |

### 7.6 Design & UX Polish (0.10)
| Score | Criteria |
|---|---|
| 5–6 | Design tokens + empty/loading/error states on every page + dark mode |
| 9–10 | + density toggle + axe-core 0 criticals + `prefers-reduced-motion` honored + Lighthouse ≥ 95 |

### 7.7 Sprint pass/fail gates
- **Sprint 1:** UpdateItem 404 returns 404; cross-tenant writes 403; GSI migration verified in CloudWatch.
- **Sprint 2:** Grep for JWT/Bearer in lambda/ returns zero matches; session validation 401s on invalid token; WAF attached; forgot-password round-trip works.
- **Sprint 3:** Concurrent-edit 412; double-POST identical; soft delete + restore; purge after 30d.
- **Sprint 4:** X-Ray trace end-to-end; DLQ receives forced-failure messages; canary green 24h.
- **Sprint 5:** Live barcode scan populates form; cache-hit path verified.
- **Sprint 6:** 800-row async import completes; forecast populates for ≥7 txns.
- **Sprint 7:** PO receive atomic across ≥3 line items; delete supplier with open PO returns 409.
- **Sprint 8:** Flag-off regression clean; transfer conserves totals.
- **Sprint 9:** Webhook signature verifies; report PDF opens.
- **Sprint 10:** p95 ≤ 400ms; ZAP 0 High; Lighthouse ≥ 95; runbook complete.

---

## 8. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Session lookup latency regresses p95 on every proxied request | Med | Med | Module-level 60s cache in Proxy.py; DynamoDB on-demand; measure before/after in Sprint 2 |
| R2 | Sessions table grows unbounded | Low | Low | TTL on `expiresAt`; weekly CloudWatch check for item count growth rate |
| R3 | GSI backfill costs spike during migration | Med | Med | Create in off-hours; monitor consumed WCU/RCU; pause writes if > 80% cap |
| R4 | TransactWriteItems 100-item cap insufficient for bulk PO receive | Low | Med | Cap PO line items at 25; chunk larger receipts |
| R5 | Multi-location migration corrupts stock counts | Low | High | Dry-run first; verify totals pre/post; PITR snapshot before run |
| R6 | Webhook dispatcher becomes DDoS vector on user endpoints | Low | Med | Per-webhook rate limit (10/s); exponential backoff; auto-disable after 5 failures |
| R7 | WAF false-positives block legitimate users | Med | Med | Start in Count mode for 48h; review sampled requests; promote to Block |
| R8 | CloudFront OAC rollout breaks S3 direct access | Low | Med | Keep S3 website endpoint enabled 72h as rollback |
| R9 | SES sandbox blocks forgot-password emails | High | Med | Document sandbox exit as a launch-blocker in Sprint 2 manual tasks; fall back to manually verifying test recipients during development |
| R10 | Manual deploy drift (Lambda code vs layer version mismatch) | High | Med | `scripts/deploy_all.sh` lists each Lambda's `LastModified` + layer version; user reviews diff before deploy |
| R11 | Generator reintroduces JWT despite instructions | Med | High | Evaluator auto-fail rule §7.1; explicit grep for jwt/jsonwebtoken/Bearer tokens |
| R12 | Session rotation on password reset misses devices | Low | Med | Bulk delete uses `Sessions.userID-index` GSI; cover with test in Sprint 2 acceptance |

---

## 9. Out of Scope (explicit)

- Native mobile apps (iOS/Android)
- Serial / lot / batch tracking
- Manufacturing / BOM
- Multi-currency
- SSO / SAML / SCIM / OAuth social login
- Per-user RBAC beyond owner
- Real-time collaboration (websockets)
- AI-generated product descriptions
- Shopify / WooCommerce integrations
- Offline-first PWA
- **Cognito migration** (revisit in v4 if SSO/multi-tenant admin is required)
- **JWT** (permanently out of scope for this project; see §1.1)
- CI/CD auto-deploy pipelines (user requirement: manual only)

---

## 10. Deployment Playbook (repeat per sprint)

1. `git pull && git status` — confirm clean tree.
2. For each changed Python Lambda:
   - `zip function.zip lambda/<Name>.py`
   - `aws lambda update-function-code --function-name <Name> --zip-file fileb://function.zip --publish`
3. For Authentication.mjs:
   - `cd lambda && zip -r auth.zip Authentication.mjs node_modules package.json`
   - `aws lambda update-function-code --function-name Authentication --zip-file fileb://auth.zip`
4. Layer updates: `bash scripts/update_all_layers.sh <new-layer-arn>`.
5. Frontend: `aws s3 sync frontend/ s3://<bucket>/ --delete --cache-control "public, max-age=60"`. Once CloudFront is live: `aws cloudfront create-invalidation --distribution-id <id> --paths "/*"`.
6. New API Gateway routes: Console → Resources → Deploy API → stage `prod`.
7. Run `gan-harness/tests/sprint<N>_smoke.sh`.
8. Tail CloudWatch logs for 5 min; verify no unexpected 5xx.

The user executes these steps. The Generator writes the code; it does NOT run `aws` or `zip` commands.

---

## 11. Generator Instructions

1. **NO JWT. Ever.** Do not import `jsonwebtoken`. Do not hand-roll HMAC token signing. Do not use `Authorization: Bearer`. Use `X-Session-Token` header + DynamoDB `Sessions` table. If you catch yourself typing `jwt`, stop.
2. **Respect manual deploy rule.** No GitHub Actions. No auto-deploy scripts. Every sprint ends with the playbook in §10.
3. **Read `.wolf/cerebrum.md` and `.wolf/buglog.json`** before writing code.
4. **Prefer editing existing files** over creating new ones unless this spec names a new file.
5. **Keep Tailwind via CDN.** No build step. No frontend npm.
6. **One sprint at a time.** Do not advance until current sprint's acceptance gates are green.
7. **Log every bug fix** to `.wolf/buglog.json`. Log every architectural decision to `.wolf/cerebrum.md` Decision Log.
8. **Grep yourself.** Before declaring a sprint done, run `grep -r -i "jwt\|jsonwebtoken\|bearer\|HS256\|RS256" lambda/ frontend/` and confirm zero matches (outside comments that reference the ban).
