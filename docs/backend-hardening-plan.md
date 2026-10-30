# Backend hardening plan (pre-launch, near-$0)

Source: live AWS audit 2026-10-31 (account 023202272390, us-east-1 only). Full evidence: the audit write-up from that session; summary below.

**Budget rule:** no users yet, so every step must keep the bill at ~$0–1/month. Current run rate ≈ $0.50/mo (mostly one Secrets Manager secret). Anything that adds a fixed monthly fee is deferred to launch (see "Not now").

Each phase is one `/factory` job (or a console checklist you do yourself). Phases are ordered by risk removed per dollar; all cost $0 unless noted.

---

## Phase 0 — Console checklist (you, ~30 min, $0)

No code. Do these first; they are free and remove the worst risks.

- [ ] Root account MFA on.
- [ ] Service Quotas → Lambda → Concurrent executions (`L-B99A9384`) → request 1000. Today the limit is 10 and it already throttled 11 times in 30 days.
- [ ] SES → request production access (needed before reset/invite emails reach real users).
- [ ] DynamoDB → turn on deletion protection on all 11 tables.
- [ ] API Gateway `InventoryIQ-API` → delete `/suppliers` and `/suppliers/{id}` (public, no auth, point at a Lambda that doesn't exist) → deploy `prod`.
- [ ] Delete leftovers: canary results bucket + canary role, `inventoryiq-frontend-v2` bucket (site now on Cloudflare), purge `InventoryIQ-StockQueue` (3 orphan messages, no consumer).
- [ ] Remove the 3 event-source mappings on `LambdaDLQ` (DailyAlert, LowItemInsight, PurgeDeletedItems) — a stray message would trigger a purge.
- [ ] Budgets: add a *forecast* alert to "Panindo monthly $10"; delete the always-red $1 "Zero Spend" budget; create a free Cost Anomaly Detection monitor.
- [ ] API Gateway stage `prod` → default method throttling: rate 20, burst 40. Override `/auth/*` and `/barcode/{code}` to rate 2, burst 5. (Free; caps how fast anyone can run up the bill.)
- [ ] Lambda: switch all functions to `arm64` (~20% cheaper) and 256 MB (fewer cold-start timeouts). Python/Node code has no native deps except `python_vendor/` (pure Python: sentry_sdk, certifi, urllib3), so no rebuild needed. Set Proxy timeout to 10s.

## Phase 1 — Close the tenant hole + remove the double hop (factory job, $0, saves ~50% per request)

**Problem:** backend routes trust `x-iq-user/x-iq-org/x-iq-role` headers and are guarded only by one shared API key (plaintext in Proxy's env). Anyone with the key can act as any user. Also every request = 2 API Gateway requests + 2 Lambda runs, and one key carries a 10k/day quota for all users.

**Change:**
- `Proxy.py` calls backend handlers with `lambda:InvokeFunction` instead of HTTP to `/prod/*`, passing the same API-Gateway-shaped event it builds today (same pattern `scripts/local_api.py` already uses locally). Route table: method + path → function name.
- After it works: delete the backend REST routes, the API key, the usage plan, and the `API_KEY` env var/secret (saves the $0.40/mo secret). Only `/auth/*` and `/proxy/{proxy+}` stay public.
- Move `/barcode/{code}` behind `/proxy` (needs a login; protects the upcitemdb trial quota).
- `JWT_SECRET` → SSM Parameter Store SecureString (free tier), read once per cold start in Authentication + Proxy.
- Local check: `npm run dev:local` + `scripts/local/rehearse_rollout.sh` pattern for the cut-over; old and new paths can run side by side until switched.

**Rollout:** deploy Proxy with invoke + feature flag → verify → delete old routes/key. Rotate nothing until the old path is gone.

## Phase 2 — Least-privilege IAM (factory job, $0)

All 18 Lambdas share one role with full DynamoDB/SNS/SQS/SES and Secrets Manager read/write.

- One role per function group (read-only items, item writers, org, auth, scheduled jobs, cascade delete, proxy), each scoped to the exact table ARNs (+ `/index/*`), the one topic, queue, SES identity and parameter it uses. No `dynamodb:DeleteTable`, no `sns:Publish` to phone numbers.
- Commit the policies as JSON under `scripts/iam/` so they're reviewable; apply with a dry-run-by-default script like `rollout_orgs.py`.

## Phase 3 — Query and job fixes (factory job, $0, lowers read cost as data grows)

- `GetTransactions`: new GSI on `InventoryTransactions` with `orgID` + `createdAt` sort key; query by range instead of filtering the whole history; return pages (`Limit` + cursor). Delete the full-table scan fallback (`GetTransactions.py:90-100`).
- `_org.list_user_orgs`: replace per-org `get_item` loop with one `batch_get_item`.
- `DailyAlert`: stop scanning every item; query per org via `orgID-index` (or a sparse `expiresAt` GSI if expiring-only), 512 MB / 30s timeout.
- `CascadeDeleteUser` stream mapping: max 3 retries, bisect on error, on-failure → an SQS DLQ.
- Scheduled jobs: 2 retries + DLQ; fix schedule time zone (Pacific/Honolulu → Asia/Manila).
- TTL: add `ttl` to `OrgInvites` (expired invites) — leave `InventoryTransactions` (it's the audit trail).

## Phase 4 — Free monitoring (factory job or console, $0)

Fits in CloudWatch free tier (10 alarms):
- Lambda `Throttles` > 0 (account), `Errors` on Proxy/Authentication, API Gateway `5XXError`, DLQ depth > 0, SES bounce rate. All → existing email.
- API Gateway access logs on `prod` with 7-day retention (source IP for abuse tracing; pennies at current volume).

## Phase 5 — At launch (adds cost; do only when there are users)

- Per-store alert emails instead of one all-stores SNS report (`InventoryIQ-Alerts`) — **must** land before a second real store exists.
- Cognito (decided 2026-10-29) replaces the custom JWT: real logout/revocation, MFA, lockout.
- Cloudflare rate-limit rule in front of `/auth/*` (free plan has 1 rule).

## Not now (cost money, low value with zero users)

| Item | Why skip | Revisit when |
|---|---|---|
| AWS WAF | ~$5+/mo fixed | Stage throttles + Cloudflare aren't enough |
| GuardDuty | ~$1–4/mo | Paying customers |
| CloudTrail trail | 90-day event history is free already | Compliance asks |
| AWS Backup plan | PITR (35 days) + manual backups cover it | Data you can't recreate |
| Provisioned concurrency | Fixed hourly fee | Cold starts measurably hurt users |
| API Gateway → HTTP API migration | ~70% cheaper per request but a rewrite | >1M requests/mo |

## Expected bill after all phases

≈ $0.10–0.50/month at today's traffic (secret removed; everything else inside free tier).
