# InventoryIQ — Product Specification v2

> Generated: 2026-04-13
> Supersedes: `gan-harness/spec.md` (v1, 8-week production hardening)
> Audience: GAN Generator agent (implementation) + Evaluator agent (scoring)
> Deployment mode: **MANUAL ONLY** — no auto-deploy, no CI/CD triggers. Every backend change lists explicit `zip` + `aws lambda update-function-code` steps.

---

## 1. Executive Summary

InventoryIQ is a serverless, multi-tenant inventory management app on AWS (Lambda + DynamoDB + API Gateway + SNS + SQS + S3). v1 of this spec focused on production hardening (JWT auth, atomic writes, observability, barcode + CSV + forecasting features). v2 reframes the work as a **12-week program** that takes InventoryIQ from "working MVP" to "credible production SaaS comparable to entry-tier Zoho Inventory / inFlow / Sortly."

**v2 adds on top of v1:**
- Single-table DynamoDB migration path (optional sprint 10-11) with GSI strategy
- Idempotency keys on all mutating endpoints (Stripe-style `Idempotency-Key` header)
- Dead-letter queues on every async Lambda + SQS consumer
- Lambda Power Tuning sweep + provisioned concurrency on hot paths
- AWS WAF in front of API Gateway (bot control + rate limit rule)
- S3 + CloudFront + OAC for frontend (replaces direct S3 website hosting)
- Reserved concurrency + throttling budget per user
- Supplier / PO (purchase order) model — the single biggest missing domain feature vs competitors
- Multi-warehouse ("location") support behind a feature flag (deferred in v1, re-scoped here)
- Customer-facing audit export (CSV + JSON) for compliance
- Design system refresh: tokens file, dark-mode toggle, density controls, empty/loading/error state library

**v2 keeps the v1 sprint numbering (1–8) and appends 9–12.** Sprints 1–8 from v1 are preserved verbatim as the baseline; the delta below augments their acceptance criteria and adds four new sprints.

---

## 2. Current State Assessment

### 2.1 What works today (verified against `.wolf/anatomy.md` + `CLAUDE.md`)
- Multi-page vanilla JS frontend with Tailwind CDN, 5 protected pages + login
- Proxy.py hides `x-api-key` from browser; `/auth/*` bypasses proxy
- sessionStorage-based pseudo-auth (UUID token, no server validation)
- Items scoped by `userID` (email) on writes
- SNS email alerts + SQS events for low stock, 24h cooldown via sentinel DynamoDB row
- Category soft-delete (reassign to "Uncategorized")
- Transaction audit log (`create`/`stock_in`/`stock_out`/`update`/`delete`)
- Manual stock adjustment modals + inline category dropdown
- CSV export + print report + search/filter on inventory and transactions

### 2.2 Known gaps (carried from v1 planning)
| Area | Gap | Severity |
|---|---|---|
| Auth | sessionStorage trust model; no server-side token validation | CRITICAL |
| Auth | No rate limiting on `/auth/login`; brute-force possible | HIGH |
| Auth | No password complexity enforcement | HIGH |
| Auth | No forgot-password flow | MEDIUM |
| DB | `GetAllItems` / `GetCategories` / `LowItemInsight` use `Scan` — O(N) cost + noisy-neighbor risk | HIGH |
| DB | No `version` field → last-write-wins on concurrent edits | HIGH |
| DB | Non-atomic item + transaction writes → audit log can diverge from state | HIGH |
| API | Proxy.py has `urllib.parse.quote` gaps on query strings + no timeout | MEDIUM |
| API | CORS `*` on all Lambdas | MEDIUM |
| Ops | No structured logging, no CloudWatch alarms, no PITR | MEDIUM |
| Ops | No DLQ on SQS `StockQueue` or on async Lambdas | MEDIUM |
| Features | No barcode, no CSV import, no forecasting, no suppliers, no POs, no multi-location | v2 scope |
| CDN | Frontend on S3 website endpoint (no CloudFront, no HTTPS on origin) | MEDIUM |
| Abuse | No WAF in front of API Gateway | MEDIUM |

### 2.3 Gap analysis vs production inventory SaaS

| Feature | Zoho | inFlow | Sortly | Cin7 | InventoryIQ today | v2 priority | Effort |
|---|---|---|---|---|---|---|---|
| Multi-user auth + RBAC | Yes | Yes | Yes | Yes | Pseudo-auth only | P0 | L |
| Barcode scanning | Yes | Yes | Yes | Yes | No | P1 | M |
| CSV import/export | Yes | Yes | Yes | Yes | Export only | P1 | M |
| Low-stock alerts | Yes | Yes | Yes | Yes | Yes (SNS email) | done | - |
| Purchase orders | Yes | Yes | No | Yes | No | P1 | L |
| Suppliers/vendors | Yes | Yes | No | Yes | No | P1 | M |
| Multi-warehouse | Yes | Yes | Yes | Yes | No | P2 | L |
| Demand forecasting | Yes (paid) | Limited | No | Yes | No | P2 | M |
| Audit log | Limited | Yes | Yes | Yes | Yes | done | - |
| Mobile app | Yes | Yes | Yes | Yes | Responsive web only | P3 | XL |
| Custom fields | Yes | Yes | Yes | Yes | No | P3 | M |
| Webhooks / API | Yes | Limited | No | Yes | No | P3 | M |
| Reports/Dashboards | Yes | Yes | Limited | Yes | Basic insights | P2 | M |
| Serial/lot tracking | Yes (paid) | Yes (paid) | No | Yes | No | out-of-scope | - |

**Takeaway:** v2 must close P0 (auth) and P1 (barcode, CSV import, suppliers, POs) to be credible. P2 (multi-warehouse, forecasting, richer dashboards) lands in sprints 9–11. P3+ is explicitly deferred.

---

## 3. v2 Sprint Plan (12 weeks)

Each sprint is **one week**. Each sprint lists: goals, code changes (frontend/backend file names), manual AWS tasks (separate section), acceptance criteria, and evaluator test scenarios. **Sprints 1–8 are the v1 spec plus v2 deltas. Sprints 9–12 are new.**

### Sprint 1 — Deploy + Verify (unchanged from v1)
**Goals:** Fix the UpdateItem.py shadowing bug, migrate reads to GSI, add ownership checks.

**Code changes:**
- `lambda/UpdateItem.py`: fix line ~56 variable shadowing that returns 500 on 404 path; return proper 404/403.
- `lambda/AddItem.py`, `UpdateItem.py`, `DeleteItem.py`: add ownership check — read item first, compare `userID` to request `userID`, return 403 on mismatch.
- `lambda/GetAllItems.py`, `GetCategories.py`, `LowItemInsight.py`, `GetTransactions.py`: convert `Scan` → `Query` on `userID-index` GSI.

**Manual AWS tasks:**
1. DynamoDB → `InventoryIQ` → Indexes → Create GSI `userID-index` (PK: `userID`, projection: ALL).
2. DynamoDB → `InventoryTransactions` → Create GSI `userID-createdAt-index` (PK: `userID`, SK: `createdAt`, projection: ALL).
3. Wait for GSI status = Active (5–15 min).
4. For each edited Lambda: `zip function.zip lambda/<Name>.py && aws lambda update-function-code --function-name <Name> --zip-file fileb://function.zip`.

**Acceptance:**
- [ ] `PUT /items/{nonExistentID}` → 404 (not 500)
- [ ] `PUT /items/{otherUsersItemID}` → 403
- [ ] `DELETE /items/{otherUsersItemID}` → 403
- [ ] `GET /items?userID=...` still returns correct data but via Query not Scan (verify in CloudWatch: `ConsumedReadCapacityUnits` drops for multi-user table)

**v2 delta:** add a smoke-test script `gan-harness/tests/sprint1_smoke.sh` the Evaluator can `curl` against the deployed proxy endpoint.

---

### Sprint 2 — Security Hardening (v1 + v2 delta)
**v1 goals retained:** JWT on login/register, Proxy.py verifies JWT, CORS locked down, rate limiting, password complexity, input validation.

**Code changes (v1):**
- `lambda/Authentication.mjs`: sign JWT with `jsonwebtoken` (HS256, 8h exp), claims `{sub, email, iat, exp}`; add rate limiter (5 failures / 15 min keyed by email in a `AuthAttempts` DynamoDB table with TTL); enforce password regex `^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$`.
- `lambda/Proxy.py`: `verify_jwt(authorization_header)` before forwarding; reject with 401 if missing/expired/tampered; derive `userID` from JWT `email` claim and **inject** into forwarded request (do not trust client-supplied `userID`).
- All write Lambdas: read `userID` from a server-injected header (e.g. `x-iq-user`) set by Proxy.py, not from body.
- `frontend/api.js`: send `Authorization: Bearer <jwt>`; handle 401 → redirect to `login.html?expired=1`.
- `frontend/login.html`, `utils.js`: store JWT in sessionStorage; decode exp; `setInterval` check every 60s.
- Input validation module `lambda/_validation.py` (shared via Lambda Layer OR copy-pasted — see §4.3).
- All Lambdas: read `CORS_ORIGIN` env var; echo only if request `Origin` matches.

**v2 delta — additions to Sprint 2:**
- **Idempotency keys.** Every POST/PUT/DELETE accepts optional `Idempotency-Key` header. Store `{key, userID, request_hash, response_body, expires_at}` in new `IdempotencyKeys` DynamoDB table with 24h TTL. On replay: return cached response, never re-execute.
- **AWS WAF.** Attach WebACL to API Gateway stage with: AWS-managed `CommonRuleSet`, `KnownBadInputsRuleSet`, rate-based rule (1000 req/5min per IP).
- **Secrets rotation plan.** Move `API_KEY` out of Lambda env vars into AWS Secrets Manager; `Proxy.py` fetches once per warm start, caches 5 min.

**Manual AWS tasks (v2 additions):**
1. Create DynamoDB `AuthAttempts` table: PK=`email`, TTL attr=`ttl`, on-demand.
2. Create DynamoDB `IdempotencyKeys` table: PK=`key`, TTL attr=`expires_at`, on-demand.
3. Secrets Manager → Store secret `inventoryiq/api-key` with value of current `x-api-key`.
4. IAM → grant Proxy Lambda role `secretsmanager:GetSecretValue` on that ARN.
5. WAF & Shield → Web ACLs → Create `inventoryiq-prod` → attach managed rule groups + rate rule → associate with API Gateway stage `/prod`.
6. Re-zip and update Proxy.py, Authentication.mjs, and each inventory Lambda.

**Acceptance (v2 additions):**
- [ ] Replay POST with same `Idempotency-Key` within 24h returns identical body and does not create duplicate item
- [ ] WAF console shows non-zero request count and blocks on synthetic SQLi payload
- [ ] Rotating the secret in Secrets Manager takes effect within 5 minutes without redeploy

---

### Sprint 3 — Data Integrity (v1 + v2 delta)
**v1 goals retained:** TransactWriteItems on all mutations, optimistic locking via `version` + ConditionExpression, Proxy.py URL encoding + 10s timeout + 1 retry on 5xx, 8h session expiry.

**Code changes (v1):** already spelled out in `gan-harness/spec.md`; preserved here by reference.

**v2 delta:**
- **Schema version field** on every item: `schemaVersion: 1`. Migrations in sprint 10 bump this. Generator backfills existing items with a one-time script `scripts/backfill_schema_version.py` (local invoke, not a Lambda).
- **ETag / If-Match.** UpdateItem returns `ETag: "<version>"`; client must send `If-Match: "<version>"`. This is a stronger framing of "optimistic locking" that also works well with HTTP caches.
- **Soft delete.** Replace hard delete with `deletedAt` + `deletedBy` fields; `GetAllItems` filters `attribute_not_exists(deletedAt)`. Add `POST /items/{id}/restore` endpoint for 30 days. Hard-purge via EventBridge scheduled Lambda after 30 days.

**Manual AWS tasks (v2 additions):**
1. Create Lambda `PurgeDeletedItems.py`; EventBridge rule `rate(1 day)` invokes it.
2. No new tables (soft delete reuses `InventoryIQ`).

**Acceptance (v2 additions):**
- [ ] Deleting an item keeps it in DB with `deletedAt` set; `GET /items` excludes it
- [ ] `POST /items/{id}/restore` within 30d restores visibility
- [ ] After 30d, `PurgeDeletedItems` removes the row
- [ ] UpdateItem without `If-Match` returns 428 Precondition Required
- [ ] UpdateItem with stale `If-Match` returns 412 Precondition Failed

---

### Sprint 4 — Observability + Resilience (v1 + v2 delta)
**v1 goals retained:** Structured JSON logging, CloudWatch alarms, PITR, error sanitization, CloudWatch dashboard.

**v2 delta:**
- **Dead-letter queues** on every async path:
  - SQS `StockQueue` → add `StockQueueDLQ` (maxReceiveCount=3).
  - Lambdas invoked async (DailyAlert, PurgeDeletedItems, LowItemInsight SNS publish path): configure `DeadLetterConfig` on each function pointing to a new `LambdaDLQ` SQS queue.
- **X-Ray tracing** enabled on all Lambdas + API Gateway stage.
- **Embedded Metrics Format (EMF) logs.** Replace ad-hoc CloudWatch PutMetricData with EMF JSON in logs → free custom metrics `iq.requests`, `iq.errors`, `iq.latency_ms` with dims `{function, userID_hash}`.
- **CloudWatch Contributor Insights** rule on `InventoryIQ` table → detect top talkers (partition hotspots).
- **Synthetic canary** (CloudWatch Synthetics, Node.js runtime): hits `/auth/login` with a canary account and `GET /items` every 5 min; alarms on 2 consecutive failures.

**Manual AWS tasks:**
1. SQS → create `StockQueueDLQ` and `LambdaDLQ`. Update `StockQueue` redrive policy.
2. Lambda console → each async-invoked Lambda → Configuration → Asynchronous invocation → DLQ = `LambdaDLQ`.
3. Lambda console → each function → Configuration → Monitoring → enable Active tracing.
4. API Gateway → stage `prod` → Logs/Tracing → enable X-Ray.
5. CloudWatch → Synthetics → create canary `iq-auth-canary` (5-min cadence, alarm on 2/3 failures).
6. DynamoDB → each table → Contributor Insights → Enable.

**Acceptance:**
- [ ] X-Ray service map shows end-to-end trace from API GW → Proxy → inventory Lambda → DynamoDB
- [ ] Failing a Lambda 3× causes message to appear in `LambdaDLQ`
- [ ] Canary dashboard shows green for 24h; a forced failure pages via SNS
- [ ] EMF custom metric `iq.latency_ms` visible in CloudWatch Metrics

---

### Sprint 5 — Barcode Scanning (v1 retained, v2 delta minor)
**v1 goals retained:** QuaggaJS camera scanner on `add-item.html`, `BarcodeLookup.py` Lambda hitting Open Food Facts + UPC Item DB with DynamoDB cache, barcode field stored + searchable.

**v2 delta:**
- Cache TTL: 30 days on product lookups (`BarcodeCache` table, TTL attr).
- Scanner also usable from `inventory.html` (mobile) to quickly stock-in/stock-out by scanning.
- Graceful degradation: if `getUserMedia` denied, show manual entry + file-upload (decode from photo) fallback.

---

### Sprint 6 — Bulk CSV Import + Enhanced Export (v1 retained, v2 delta)
**v1 goals retained:** `BulkImport.py`, drag-and-drop modal, per-row error reporting, 500-item cap, downloadable template.

**v2 delta:**
- **Async import for files > 100 rows.** Small imports run inline. Larger uploads: frontend POSTs CSV to a pre-signed S3 URL; S3 `ObjectCreated` triggers `BulkImportAsync.py`; progress tracked in `ImportJobs` table; frontend polls `GET /import/{jobId}`.
- **Export enrichments:** export includes `version`, `schemaVersion`, `deletedAt`, `supplierID` (see sprint 9).
- **JSON export** in addition to CSV (`Accept: application/json`).

---

### Sprint 7 — Demand Forecasting (v1 retained, v2 delta)
**v1 goals retained:** Weighted moving average from `stock_out` history, days-until-stockout, confidence levels, reorder list, forecast page with urgency cards.

**v2 delta:**
- **Seasonality flag (optional):** if ≥ 180 days of history, compute simple 7-day and 30-day seasonality indices; surface "weekly peak" day.
- **Forecast explainability:** endpoint response includes `{method, sampleSize, windowDays, lastUpdated}` so UI can render "Why this number?" tooltip.
- **Reorder point auto-suggestion:** `suggestedThreshold = ceil(dailyBurn × leadTimeDays × safetyFactor)` with `leadTimeDays` defaulting to 7 (overridable per supplier in sprint 9).

---

### Sprint 8 — Polish + Launch (v1 retained, v2 delta)
**v1 goals retained:** Forgot-password flow, security audit, launch checklist.

**v2 delta:**
- **Design pass:** introduce `frontend/design-tokens.css` (CSS custom properties), dark-mode toggle in header, density toggle (comfortable/compact), full empty/loading/error state library.
- **Accessibility audit:** axe-core run on every page; target zero critical issues; keyboard nav for all modals; `prefers-reduced-motion` respected.
- **Docs:** user-facing `docs/user-guide.md` + API reference in OpenAPI 3.0 (`docs/openapi.yaml`).

---

### Sprint 9 — Suppliers + Purchase Orders (NEW in v2)

**Goal:** Close the single biggest feature gap vs Zoho/inFlow — give users a way to model where stock comes from and trigger/receive POs.

**Data model additions (same InventoryIQ table with new PK schema, OR new tables — see §4.2):**
- `Suppliers`: `supplierID` (PK), `userID`, `name`, `contactEmail`, `phone`, `address`, `leadTimeDays`, `notes`
- `PurchaseOrders`: `poID` (PK), `userID`, `supplierID`, `status` (draft/sent/partial/received/closed), `createdAt`, `sentAt`, `expectedAt`, `receivedAt`, `lineItems: [{itemID, qty, unitCost}]`, `totalCost`
- Items gain optional `supplierID` + `preferredSupplierLeadTimeDays`.

**New Lambdas:**
- `CreateSupplier.py`, `GetSuppliers.py`, `UpdateSupplier.py`, `DeleteSupplier.py`
- `CreatePO.py`, `GetPOs.py`, `UpdatePO.py`, `ReceivePO.py` (atomic: increments item.quantity via TransactWriteItems across all line items; logs `stock_in` transactions for each line with `notes: "PO <poID>"`)

**New API routes (behind Proxy):**
- `GET/POST /suppliers`, `PUT/DELETE /suppliers/{id}`
- `GET/POST /purchase-orders`, `PUT /purchase-orders/{id}`, `POST /purchase-orders/{id}/receive`

**New frontend pages:**
- `suppliers.html` — table + add/edit modal
- `purchase-orders.html` — list with status pills, detail view, "Mark received" action (supports partial receipt)
- Inventory row action: "Create PO" → prefills line with current item + suggested reorder qty

**Manual AWS tasks:**
1. Create `Suppliers` + `PurchaseOrders` DynamoDB tables (on-demand, GSI `userID-index`).
2. API Gateway: add 2 new resources + methods, enable Lambda Proxy Integration, redeploy stage.
3. Deploy 8 new Lambdas individually.

**Acceptance:**
- [ ] Create supplier → appears in list → assignable on item detail
- [ ] Create PO from inventory row → line item prefilled with suggested reorder qty
- [ ] Mark PO received (full) → all line items' `quantity` increments atomically → transactions logged with PO reference
- [ ] Mark PO received (partial) → status becomes `partial`, remaining qty tracked
- [ ] Deleting a supplier with open POs → 409 with list of blocking PO IDs

---

### Sprint 10 — Multi-Warehouse / Locations (NEW in v2, feature-flagged)

**Goal:** Support users who stock the same SKU in multiple physical locations. Off by default behind a per-user feature flag (`features.multiLocation: true`) set manually or via an admin endpoint.

**Data model migration:**
- New `Locations` table: `locationID` (PK), `userID`, `name`, `address`, `isDefault`.
- Items decompose: the existing `InventoryIQ` row becomes the "product" definition (name, desc, price, thresholds). Stock-on-hand moves into a new composite row or `ItemStock` table: PK=`itemID`, SK=`locationID`, attrs=`quantity`, `lowStockThreshold` (per-location override optional), `updatedAt`.
- Transactions gain `locationID`.
- Migration script `scripts/migrate_to_locations.py`: for each existing item, create one `ItemStock` row with `locationID=<user's default location>` and the item's current `quantity`; bumps item `schemaVersion` → 2.

**Transfers between locations:**
- New endpoint `POST /transfers` with `{itemID, fromLocationID, toLocationID, qty}` — atomic: two transaction log entries (`stock_out` from source, `stock_in` to dest) + two ItemStock mutations in a single `TransactWriteItems` call.

**Frontend:**
- New `locations.html` page
- Inventory table: location dropdown in header filters stock view
- Item detail: stacked per-location stock breakdown with transfer button

**Manual AWS tasks:**
1. Create `Locations` + `ItemStock` tables (on-demand, GSI `userID-index`).
2. Run migration script from a local machine with `AWS_PROFILE` set; dry-run mode first.
3. Deploy new Lambdas + redeploy affected existing Lambdas (GetAllItems, AddItem, UpdateItem now join with ItemStock).

**Acceptance:**
- [ ] Feature flag off: UI identical to sprint 9, all flows unchanged
- [ ] Feature flag on: location selector appears, default location auto-created with all existing stock
- [ ] Transfer 5 units A→B: both transaction rows logged, totals conserved
- [ ] Low-stock alerts aggregate across locations but can also scope per-location

---

### Sprint 11 — Reporting + Webhooks (NEW in v2)

**Goal:** Ship the "reports" tab customers expect + let power users integrate via webhooks.

**Reports (`reports.html`):**
- Inventory valuation (qty × price per category + total)
- Stock movement over time (line chart: daily stock_in vs stock_out)
- Top-N fastest-moving + slowest-moving SKUs
- Dead stock (no movement > 90 days)
- CSV + PDF export (PDF via server-side `ReportPDF.py` using reportlab — deploy as Lambda Layer)
- Date range picker, category + supplier filters

**Webhooks:**
- `Webhooks` table: `webhookID` (PK), `userID`, `url`, `secret`, `events: [item.created, item.updated, stock.low, po.received, ...]`, `active`, `createdAt`, `lastDeliveryStatus`
- `WebhookDispatcher.py` Lambda subscribed to an SNS topic `inventoryiq-events` that every mutating Lambda publishes to. Delivers HMAC-SHA256-signed JSON payloads. DLQ on 5 consecutive failures → auto-disable + email user.
- `settings.html` page: add/remove webhooks, view delivery log (last 50 attempts).

**Manual AWS tasks:**
1. Create SNS topic `inventoryiq-events`.
2. Grant every mutating Lambda `sns:Publish` on that topic.
3. Create `Webhooks` + `WebhookDeliveries` tables.
4. Deploy `WebhookDispatcher.py` + subscribe to SNS topic.
5. Deploy `ReportPDF.py` with reportlab Layer (pre-built ARN from a public layer repo OR user builds with `pip install -t python/ reportlab && zip -r layer.zip python`).

**Acceptance:**
- [ ] Register a webhook to `https://webhook.site/<id>` → create an item → payload arrives with valid HMAC signature
- [ ] Webhook URL returning 500 five times in a row → auto-disables and emails user
- [ ] Reports page renders valuation within 2s for 1000-item inventory
- [ ] PDF export downloads and opens in Preview/Acrobat

---

### Sprint 12 — Performance, Cost, and Launch (NEW in v2)

**Goal:** Power-tune, lock down costs, final pre-launch gates.

**Performance:**
- Run [AWS Lambda Power Tuning](https://github.com/alexcasalboni/aws-lambda-power-tuning) state machine against all Python Lambdas; set memory per recommendation (typically 512–1024 MB for this workload).
- Provisioned concurrency on `Proxy.py` (1–2) and `GetAllItems.py` (1) to kill cold starts on the critical path.
- Frontend: move S3 website → **CloudFront + Origin Access Control**. Enable Brotli compression. Set long cache + content-hashed filenames for `style.css`, `utils.js`, `api.js`, `config.js` (manual hash-stamping acceptable given no build step).

**Cost:**
- Budgets: AWS Budgets alert at $5, $20, $50/month with email to user.
- DynamoDB: confirm on-demand billing unless sustained > 25% of provisioned equivalent (then switch).
- Lambda: set reserved concurrency caps to bound worst-case spend (e.g., 50 per function).
- CloudFront: price class `PriceClass_100` (US/EU only).

**Launch gates:**
- Pen-test checklist (OWASP ASVS L1 minimum): run `zap-baseline.py` against production URL; triage findings.
- Back-up test: restore PITR to a new table; spot-check 10 rows.
- Runbook `docs/runbook.md`: incident response, common errors, rollback steps (each Lambda has `aws lambda update-function-code --function-name X --s3-bucket iq-lambda-archive --s3-key <prev-version>.zip` instructions).
- Status page: a simple `status.html` page served from S3 reading a JSON heartbeat the canary writes.

**Acceptance:**
- [ ] p95 latency on `GET /items` ≤ 400 ms from US-East test client
- [ ] Cold-start rate on `Proxy.py` < 2% over 1h of synthetic traffic
- [ ] Monthly cost at 100 MAU projected ≤ $15
- [ ] OWASP ZAP baseline scan: 0 High, ≤ 3 Medium with documented accept/mitigate
- [ ] Restored-from-PITR row matches original byte-for-byte

---

## 4. Technical Architecture Changes (v2)

### 4.1 Target architecture
```
                                   ┌──────────────┐
   Browser ── HTTPS ── CloudFront ─┤ S3 (static)  │
                 │                 └──────────────┘
                 │
                 └──── HTTPS ──► API Gateway (/prod/proxy/*)
                                    │  (WAF attached)
                                    ▼
                                 Proxy.py ── verify JWT
                                    │  ── inject x-iq-user header
                                    │  ── inject x-api-key from Secrets Manager
                                    ▼
                              API Gateway (/prod/*)  ── WAF
                                    │
                     ┌──────────────┼─────────────┬──────────────┐
                     ▼              ▼             ▼              ▼
                Inventory      Auth         Reports /        Webhooks
                Lambdas        Lambda       PDF Lambda       Dispatcher
                     │              │             │              │
                     ▼              ▼             ▼              ▼
                DynamoDB        DynamoDB     DynamoDB         SNS Topic
                (items,         (Users,      (aggregations)   ── SQS (DLQ)
                 stock,          Auth
                 txns,           Attempts,
                 POs,            Idempotency
                 suppliers)      Keys)
```

### 4.2 DynamoDB strategy — when to stay multi-table vs. go single-table
**Decision:** stay multi-table through Sprint 11. Evaluate single-table only as a Sprint 12 stretch.
- Rationale: migration risk is high; our access patterns are modest (≤ a few dozen per user); the multi-table model is legible to new contributors; GSI costs are fine at on-demand.
- If we do migrate: one table `InventoryIQ-Main`, PK=`PK`, SK=`SK`, composite keys like `USER#<email>` / `ITEM#<id>`, `ITEM#<id>` / `TXN#<ts>#<uuid>`, `USER#<email>` / `PO#<id>`, with GSI1 = inverted, GSI2 = `userID` + `createdAt` for time-range reads.

### 4.3 Shared validation
Because there is no build step, put shared Python utilities in a **Lambda Layer** named `iq-common` with:
- `_validation.py` — `validate_item_payload(body) -> (ok, errors)`; enforces `name` 1–200 chars, `price >= 0`, `quantity >= 0 and int`, `lowStockThreshold >= 0`, description ≤ 2000 chars, email regex
- `_logging.py` — `log_json(event, level='INFO', **kwargs)` wrapping `logging` with EMF extension
- `_idempotency.py` — decorator that reads `Idempotency-Key` header and short-circuits
- `_auth.py` — `get_user_from_event(event)` reads `x-iq-user` injected by Proxy.py
- `_response.py` — `ok(body)`, `err(status, message, **extra)`, all with CORS headers from env

Layer built locally: `cd layer && pip install -t python/ pydantic && zip -r layer.zip python && aws lambda publish-layer-version --layer-name iq-common --zip-file fileb://layer.zip`. Each Lambda attaches via `aws lambda update-function-configuration --function-name X --layers <layer-arn>`.

### 4.4 Error envelope
All Lambdas return JSON:
```json
{ "error": { "code": "VALIDATION_FAILED", "message": "quantity must be >= 0", "field": "quantity", "requestId": "..." } }
```
Codes: `VALIDATION_FAILED`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `PRECONDITION_FAILED`, `RATE_LIMITED`, `INTERNAL`.

---

## 5. Evaluation Rubric v2

Weights retained from v1 but two new categories appended for v2 scope. Final score = weighted sum (0–10 each).

| # | Category | Weight | v1? |
|---|---|---|---|
| 1 | Security | 0.25 | v1 0.30, slightly reduced |
| 2 | Data Integrity | 0.20 | v1 0.25 |
| 3 | Resilience & Observability | 0.15 | v1 0.30 total |
| 4 | Features (v1: barcode/CSV/forecast) | 0.15 | v1 0.15 |
| 5 | **Domain Features (suppliers/PO/locations/reports)** | 0.15 | NEW |
| 6 | **Design & UX Polish** | 0.10 | NEW |

**v1 rubric detail (Security, Data Integrity, Resilience, Observability, Features) carries over from `gan-harness/eval-rubric.md` unchanged.** Two new rubrics below.

### 5.5 Domain Features (weight 0.15)
| Score | Criteria |
|---|---|
| 0–2 | Suppliers/PO not implemented |
| 3–4 | Supplier CRUD works but POs missing or can't receive |
| 5–6 | Full supplier + PO lifecycle including partial receipt + atomic stock-in on receive |
| 7–8 | All of above + reports page with valuation, movement, top-N, dead stock + PDF export |
| 9–10 | All of above + webhooks with HMAC signing + delivery log + auto-disable on repeated failure + multi-location feature behind flag with transfer flow |

### 5.6 Design & UX Polish (weight 0.10)
| Score | Criteria |
|---|---|
| 0–2 | No tokens file, inconsistent spacing, no empty states |
| 3–4 | Design tokens introduced but only partially adopted |
| 5–6 | Tokens adopted everywhere, dark mode works, core empty/loading/error states on each page |
| 7–8 | All of above + keyboard navigation in modals + axe-core 0 criticals + density toggle |
| 9–10 | All of above + `prefers-reduced-motion` honored + Lighthouse ≥ 95 on Accessibility and Best Practices + status/runbook/docs polished |

### 5.7 Sprint pass/fail gates v2
Sprints 1–8 gates carry over verbatim from v1. New gates:

**Sprint 9:**
- [ ] Supplier CRUD works
- [ ] Receiving a PO atomically updates all line items + logs transactions
- [ ] Inventory row can spawn a PO prefilled with suggested reorder qty

**Sprint 10:**
- [ ] Feature flag off → zero regression from sprint 9
- [ ] Transfer between locations is atomic and logged twice (out + in)
- [ ] Totals across locations always equal sum of per-location stock

**Sprint 11:**
- [ ] Webhook signed payload verifies with shared secret
- [ ] Reports page renders within 2s at 1000 items
- [ ] PDF export opens in standard viewers

**Sprint 12:**
- [ ] p95 GET /items ≤ 400ms
- [ ] ZAP baseline: 0 High severity
- [ ] Canary green for 24h
- [ ] Cost projection documented

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | JWT rollout breaks existing sessions | High | High | Dual-mode Proxy.py for 7 days: accept legacy sessionStorage token OR JWT; after grace, require JWT. Banner on dashboard warns "re-login required by <date>" |
| R2 | GSI backfill costs spike during migration | Med | Med | Create GSI in off-hours; monitor consumed WCU/RCU; pause writes if > 80% of cap |
| R3 | TransactWriteItems quota (100 items) insufficient for bulk PO receive | Low | Med | Cap PO line items at 25 per PO; chunk larger receipts |
| R4 | Idempotency table grows unbounded | Med | Low | TTL attribute `expires_at` with 24h lifetime; weekly CloudWatch metric check |
| R5 | Multi-location migration corrupts stock counts | Low | High | Dry-run mode on migration script; verify totals pre/post; PITR snapshot before run |
| R6 | Webhook dispatcher becomes a DDoS vector on user endpoints | Low | Med | Per-webhook rate limit (10/s); exponential backoff; auto-disable after 5 failures |
| R7 | Lambda Layer `iq-common` versioning drifts across Lambdas | Med | Low | Shell script `scripts/update_all_layers.sh` to attach same layer version to every function |
| R8 | CloudFront OAC rollout breaks S3 direct access | Low | Med | Stand up CloudFront dist pointing at S3, test, then update DNS; keep S3 website endpoint enabled for rollback 72h |
| R9 | WAF false-positives block legitimate users | Med | Med | Start in `Count` mode for 48h; promote to `Block` after reviewing sampled requests |
| R10 | Manual deploy drift between environments | High | Med | `scripts/deploy_all.sh` that user runs manually; logs each Lambda's `LastModified` timestamp; checksums zip before upload |

---

## 7. Anti-AI-slop Design Direction

The current UI is functional but visually generic. v2 should feel like a **deliberate product**, not a wireframe.

- **Color system:** primary `#005ab4` (kept), secondary `#00a37a` (inventory-green), warn `#e69b00`, danger `#c82c4a`, neutral ramp `#0b1220 → #f6f8fb` (9 stops). Publish in `frontend/design-tokens.css` as CSS custom properties.
- **Typography:** Inter for UI (kept); **JetBrains Mono** for SKUs, barcodes, quantities, timestamps — monospaced tabular numbers read better in inventory tables.
- **Iconography:** one icon set only (Lucide via CDN). No mixed libraries, no emoji as icons.
- **Density:** two modes — `comfortable` (default) and `compact` (rows 32px). Toggle persists in localStorage.
- **Empty states:** every list view has an explicit empty state with an illustrative glyph (Lucide) + primary CTA ("Add your first item").
- **Loading states:** skeleton rows (not spinners) on tables; shimmer animation obeys `prefers-reduced-motion`.
- **Error states:** inline alert component with code, message, and optional retry button; never `alert()`.
- **Avoid:** gradient backgrounds on cards, unlabeled icon buttons, purple-to-pink SaaS clichés, stock photography, AI-generated hero illustrations, animated confetti, copy like "seamless", "leverage", "empower".
- **Inspiration (for Generator to reference):** Linear's density and keyboard affordances; Stripe Dashboard's tables and empty states; Tailwind UI's form primitives; Raycast's palette command.

---

## 8. File-Level Change Map (v2)

### New backend Lambdas
| File | Sprint | Purpose |
|---|---|---|
| `lambda/CreateSupplier.py` | 9 | POST /suppliers |
| `lambda/GetSuppliers.py` | 9 | GET /suppliers |
| `lambda/UpdateSupplier.py` | 9 | PUT /suppliers/{id} |
| `lambda/DeleteSupplier.py` | 9 | DELETE with 409 if open POs |
| `lambda/CreatePO.py` | 9 | POST /purchase-orders |
| `lambda/GetPOs.py` | 9 | GET /purchase-orders |
| `lambda/UpdatePO.py` | 9 | PUT /purchase-orders/{id} |
| `lambda/ReceivePO.py` | 9 | Atomic stock-in across line items |
| `lambda/CreateLocation.py` | 10 | POST /locations |
| `lambda/GetLocations.py` | 10 | GET /locations |
| `lambda/Transfer.py` | 10 | POST /transfers atomic |
| `lambda/ReportValuation.py` | 11 | GET /reports/valuation |
| `lambda/ReportMovement.py` | 11 | GET /reports/movement |
| `lambda/ReportPDF.py` | 11 | Renders reportlab PDF |
| `lambda/WebhookRegister.py` | 11 | CRUD /webhooks |
| `lambda/WebhookDispatcher.py` | 11 | SNS-triggered, HMAC-signs & POSTs |
| `lambda/PurgeDeletedItems.py` | 3 delta | EventBridge daily hard-purge |
| `lambda/BulkImportAsync.py` | 6 delta | S3-triggered large imports |

### Modified existing Lambdas (v2)
| File | Changes |
|---|---|
| `lambda/Proxy.py` | + Secrets Manager lookup, + `x-iq-user` header injection, + idempotency pass-through |
| `lambda/AddItem.py` | + soft-delete fields, + schemaVersion, + supplierID FK, + layer import |
| `lambda/UpdateItem.py` | + If-Match / ETag, + soft-delete handling, + supplierID |
| `lambda/DeleteItem.py` | → soft delete (deletedAt/By); + restore endpoint handler |
| `lambda/GetAllItems.py` | filter `attribute_not_exists(deletedAt)`, join ItemStock when feature flag on |
| `lambda/LowItemInsight.py` | aggregate across locations |
| `lambda/Authentication.mjs` | + forgot-password, + JWT signing, + rate limiting, + password regex |

### New frontend files
| File | Sprint |
|---|---|
| `frontend/design-tokens.css` | 8 |
| `frontend/suppliers.html` | 9 |
| `frontend/purchase-orders.html` | 9 |
| `frontend/locations.html` | 10 |
| `frontend/reports.html` | 11 |
| `frontend/settings.html` | 11 (webhooks) |
| `frontend/status.html` | 12 |
| `frontend/forecast.html` | 7 (from v1) |
| `frontend/import-template.csv` | 6 (from v1) |

### New docs
| File | Sprint |
|---|---|
| `docs/openapi.yaml` | 8 |
| `docs/user-guide.md` | 8 |
| `docs/runbook.md` | 12 |

### New infra/scripts
| File | Purpose |
|---|---|
| `scripts/deploy_all.sh` | Loops Lambdas, zips, updates |
| `scripts/backfill_schema_version.py` | One-shot migration |
| `scripts/migrate_to_locations.py` | Sprint 10 migration |
| `scripts/update_all_layers.sh` | Attach new layer version everywhere |
| `gan-harness/tests/*.sh` | Sprint smoke tests |

---

## 9. Deployment Playbook (manual, repeat per sprint)

Every sprint ends with a deploy checklist the user executes:

1. `git pull && git status` — confirm clean tree except the sprint's changes.
2. For each changed Python Lambda:
   `zip function.zip lambda/<Name>.py` (add `_common.py` etc. if not using Layer)
   `aws lambda update-function-code --function-name <Name> --zip-file fileb://function.zip --publish`
3. For Authentication.mjs:
   `cd lambda && zip -r auth.zip Authentication.mjs node_modules package.json && aws lambda update-function-code --function-name Authentication --zip-file fileb://auth.zip`
4. For Layer updates: `scripts/update_all_layers.sh <new-version>`.
5. For frontend:
   `aws s3 sync frontend/ s3://<bucket>/ --delete --cache-control "public, max-age=60"`
   (when CloudFront is live: also `aws cloudfront create-invalidation --distribution-id <id> --paths "/*"`)
6. For new API Gateway routes: Console → Resources → Deploy API → stage `prod`.
7. Run `gan-harness/tests/sprint<N>_smoke.sh` — all checks must pass.
8. Tail CloudWatch logs for 5 min; verify no unexpected 5xx.

---

## 10. Out of Scope (explicit)

To keep v2 deliverable, the following are **not** in this spec:
- Native mobile apps (iOS/Android)
- Serial / lot / batch tracking
- Manufacturing / BOM
- Multi-currency
- SSO / SAML / SCIM
- Per-user RBAC beyond owner (all users today are single-tenant owners)
- Real-time collaboration (websockets)
- AI-generated product descriptions
- Shopify / WooCommerce integrations
- Offline-first PWA

These are candidates for a v3 spec.

---

## 11. Generator Instructions (preamble for the implementing agent)

When implementing this spec:
1. **Respect manual deploy rule.** Never write GitHub Actions or auto-deploy scripts. Every sprint ends with a human-readable playbook.
2. **Read `.wolf/cerebrum.md` and `.wolf/buglog.json`** before writing code, per project convention.
3. **Prefer editing existing files** over creating new ones unless this spec names a new file.
4. **Keep Tailwind via CDN.** No build step. If utilities are insufficient, use `style.css` with CSS custom properties.
5. **No new npm dependencies in frontend.** Libraries like QuaggaJS, reportlab (Python), jsonwebtoken (Node) must be justified and documented.
6. **One sprint at a time.** Do not implement forward sprints until current sprint's gates pass.
7. **Every bug you fix → log to `.wolf/buglog.json`.**
8. **Every architectural choice → log to `.wolf/cerebrum.md` Decision Log.**
