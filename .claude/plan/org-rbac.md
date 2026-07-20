# Implementation Plan: Organizations, Membership & RBAC

> Source: `docs/PRD-org-membership-rbac.md` · Generated: 2026-06-26
> Dual-model analysis: **N/A** — `codeagent-wrapper` + Codex/Gemini prompts not installed on this machine. Plan synthesized by Claude from PRD + grounded reads of `lambda/Proxy.py` and `frontend/api.js`.

### Task Type
- [x] Fullstack — Backend (Python Lambdas + Proxy) + Frontend (vanilla JS/HTML)

---

## Grounding Facts (verified against code, not assumed)

| Fact | Source | Implication |
|---|---|---|
| `Proxy.py` verifies HS256 JWT **statelessly** — zero DynamoDB reads, injects only `x-iq-user` (= JWT `sub`) | `lambda/Proxy.py:68-95,166-175` | Org enforcement adds a **new** DynamoDB read to Proxy. PRD's "60s session cache" does not exist; there is nothing to invalidate — that is good. |
| Proxy strips client `x-iq-user` already (anti-spoof pattern exists) | `lambda/Proxy.py:166-167` | Extend the same strip to `x-iq-org` / `x-iq-role`. |
| Frontend sends auth via one chokepoint `authHeaders()` | `frontend/api.js:22-27` | Add `X-IQ-Org` in exactly one place; every call inherits it. |
| `/auth/*` bypasses session validation | `lambda/Proxy.py:124-125` | Invite-accept that needs a session must NOT live under `/auth/`; org context resolves post-login. |
| Data handlers trust `x-iq-user` header for tenancy today | PRD + handler pattern | Switch tenant key to `x-iq-org`; keep `x-iq-user` as actor only. |
| JWT carries only `sub` | `lambda/Proxy.py:93` | Do **not** bake role/org into JWT — that would make revoke stale. Look role up live. |

**Core design decision (recommended): no membership cache in Proxy.**
One `GetItem` on `OrgMembers` per protected request. Low-traffic SaaS → negligible cost, and it makes AC#6/#10 (instant revoke) true by construction. `ponytail: no cache; add a 10s TTL only if Proxy p99 latency measurably regresses.`

---

## Technical Solution

`orgID` becomes the tenant boundary. `userID` (email) stays as actor/account identity. Proxy resolves `(user, selected org)` → active membership + role on every request, injects trusted `x-iq-org` + `x-iq-role`, and rejects non-members. Existing handlers query by `orgID` instead of `userID`. Frontend gains an org switcher that sets `X-IQ-Org`.

Role check stays **server-side** (handlers read trusted `x-iq-role`); UI hiding is cosmetic only.

---

## Implementation Steps (phased — each phase shippable/testable before the next)

### Phase 0 — Storage + migration (no UI, no enforcement yet)
1. Create 3 DynamoDB tables (see schema). Add `orgID-index` GSI to `InventoryIQ`, `InventoryTransactions`, `Suppliers`.
2. One-shot backfill script (`scripts/migrate_orgs.py`, run locally w/ boto3):
   - For each distinct user → create `Organizations` row (`orgID=uuid4`, `ownerUserID=email`, `memberCount=1`) + `OrgMembers` row (`role=owner`, `status=active`).
   - Backfill `orgID` onto every `InventoryIQ` / `InventoryTransactions` / `Suppliers` / idempotency record owned by that user.
   - Post-check: every item has exactly one `orgID`; every user has ≥1 owner membership; no org has 0 owners.
   - **Deliverable:** populated tables, dry-run + apply modes, idempotent (safe to re-run).

### Phase 1 — Proxy tenant enforcement (the linchpin)
3. In `Proxy.py._handle`: after `user_id` resolves, read selected org from `X-IQ-Org` header.
   - If absent on a protected route → `400` (client must pick an org; frontend always sends it post-login).
   - `GetItem OrgMembers(orgID, userID)`; if missing or `status!=active` → `403`.
   - On success, in `_forward`: strip any client `x-iq-org`/`x-iq-role`, inject trusted `x-iq-org=<org>` + `x-iq-role=<role>` alongside existing `x-iq-user`.
   - **Deliverable:** every proxied request is membership-gated; removed member gets `403` next request.

### Phase 2 — Org / member / invite Lambdas
4. New handlers (reuse `_logging.response`, idempotency, Sentry conventions):
   - `Orgs.py` → `GET /orgs`, `POST /orgs/{id}/switch`, `PATCH /orgs/{id}`, `POST /orgs/{id}/transfer-owner`, `DELETE /orgs/{id}`.
   - `OrgMembers.py` → `GET /orgs/{id}/members`, `PATCH /orgs/{id}/members/{userID}`, `DELETE /orgs/{id}/members/{userID}`.
   - `OrgInvites.py` → `POST /orgs/{id}/invites`, `POST /orgs/{id}/invites/{inviteID}/revoke`, `POST /org-invites/{token}/accept`.
5. Authorization: each handler reads trusted `x-iq-role`; enforce the role matrix server-side (Viewer<Editor<Admin<Owner). Owner-only: rename/delete/transfer; Admin: members+invites; never remove/demote current Owner.
6. Invites: opaque random token, store **hash only** (`hashlib.sha256`), `expiresAt` TTL = 72h, single-use, normalized lowercase email. Reuse existing SES sender used by password reset.
7. Atomic seat cap: `memberCount` increment guarded by `ConditionExpression memberCount < 5` in the same `TransactWriteItems` that adds the member/invite (count pending + active). `ponytail: TransactWriteItems is the lazy-correct path — no app-level lock needed.`
   - **Deliverable:** full invite lifecycle (pending/accepted/expired/revoked/duplicate/resend/no-account-signup) + member CRUD.

### Phase 3 — Scope existing data handlers by orgID
8. Update read/write handlers (`GetAllItems, AddItem, UpdateItem, DeleteItem, RestoreItem, GetTransactions, GetCategories, DeleteCategory, Suppliers, BarcodeLookup, Forecast, LowItemInsight, BulkImport, BulkImportAsync, PurgeDeletedItems, DailyAlert`) to use `x-iq-org` as the query/tenant key (GSI `orgID-index`), and record `x-iq-user` as `actorUserID` on transaction writes.
9. Namespace idempotency keys with `orgID` so two orgs can reuse a client key.
10. Export gating: CSV/print endpoints (if any) require `x-iq-role in {admin,owner}`.
    - **Deliverable:** AC#11 — all data paths org-scoped; Org A cannot read Org B by swapping `X-IQ-Org` (Proxy already blocks non-members).

### Phase 4 — Frontend
11. `api.js authHeaders()`: add `'X-IQ-Org': sessionStorage.getItem('currentOrg') || ''`. (one-line chokepoint)
12. Login flow: store orgs list + default `currentOrg` from login response (or call `GET /orgs` right after).
13. Org switcher (header dropdown) → sets `currentOrg`, reloads data. Members/Team page (list, invite form w/ role select, pending list w/ revoke/resend, remove, role change). Invite-accept page (`accept.html?token=...`).
14. UI hides forbidden actions by role — cosmetic; server is source of truth.
    - **Deliverable:** AC#2/#5/#8 user flows.

### Phase 5 — Tests
15. pytest: migration, isolation (A can't touch B), role matrix, invite lifecycle, removal→403, concurrency (no 6th seat). Playwright: invite→accept→switch happy path.

---

## Key Files

| File | Operation | Description |
|---|---|---|
| `lambda/Proxy.py:148,166-175` | Modify | Resolve `X-IQ-Org`, membership `GetItem`, inject trusted `x-iq-org`/`x-iq-role`, strip spoofed copies, `403` non-members |
| `lambda/Orgs.py` | Create | Org CRUD + switch + transfer |
| `lambda/OrgMembers.py` | Create | Member list / role change / remove |
| `lambda/OrgInvites.py` | Create | Invite create / revoke / accept (token hash, TTL, SES) |
| `lambda/_logging.py` | Reuse | `response()`, `capture_error()` — no change |
| `lambda/GetAllItems.py` + 15 data handlers | Modify | Tenant key `x-iq-user` → `x-iq-org`; `actorUserID` attribution |
| `frontend/api.js:22-27` | Modify | Add `X-IQ-Org` to `authHeaders()` |
| `frontend/*.html` + new `members.html`, `accept.html` | Create/Modify | Switcher, team page, invite accept |
| `scripts/migrate_orgs.py` | Create | One-shot backfill, dry-run + apply |

## New DynamoDB Records

| Table | Key | Notes |
|---|---|---|
| `Organizations` | PK `orgID` | `name, ownerUserID, memberCount, createdAt, updatedAt, deletedAt?` |
| `OrgMembers` | PK `orgID` + SK `userID` | `role, status, joinedAt`; GSI `userID-index` for switcher; **read by Proxy every request** |
| `OrgInvites` | PK `inviteTokenHash` | `orgID, email, role, status, invitedBy, expiresAt`(TTL); GSI by `orgID` + by `email` |

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| Proxy now does a DynamoDB read per request (was pure-CPU) | No cache → correctness first; add 10s TTL only if latency regresses. OrgMembers `GetItem` is single-digit ms. |
| Migration leaves an item without `orgID` → handler can't find it | Backfill post-check + dry-run; handlers fail closed (`403`/empty) not open. |
| Seat-cap race (two concurrent invites = 6 members) | `TransactWriteItems` with `memberCount < 5` condition (AC#12). |
| Role baked into stale client/JWT bypasses revoke | Role never stored client-side for authz; Proxy looks up live every request (AC#6/#10). |
| Invite token leakage | Store hash only; opaque random; single-use; 72h TTL. |
| Cross-tenant idempotency key collision | Namespace stored key with `orgID`. |

## Sequencing note
Phases 0→1→3 must land before the UI (Phase 4) is exposed, so authorization is live before anyone can switch orgs. Phase 2 (invite Lambdas) can develop in parallel with Phase 3.

### SESSION_ID (for /ccg:execute)
- CODEX_SESSION: N/A (wrapper not installed)
- GEMINI_SESSION: N/A (wrapper not installed)
