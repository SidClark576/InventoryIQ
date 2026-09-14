# ARCHITECTURE-ESSENTIALS.md — InventoryIQ

    ARCHITECTURE-ESSENTIALS.md   read first, always (this file)
    ARCHITECTURE.md              read for structure, tables, versions
    PRD.md                       read for product intent and user-facing behavior
    AGENTS.md                    read for conventions and style rules

Every rule below is one where breaking it compiles, type-checks, and passes
review — then fails in production or silently corrupts data.

---

## 1. Wrong choice compiles

- Adding a JWT library (`jsonwebtoken`, `PyJWT`) instead of stdlib crypto/hmac
  compiles fine, works fine locally, then breaks the moment `Authentication`,
  `Proxy`, or `Authorizer` disagree on signature format. Auth is stateless
  HS256 signed/verified with stdlib only — `crypto` (Node) / `hmac`+`hashlib`
  (Python). No exceptions.
- Trusting `x-iq-user` / `x-iq-org` / `x-iq-role` from a request body or query
  param instead of the proxy-injected header compiles and passes review, then
  is a tenant-isolation bypass. These three headers, injected by `Proxy.py`
  after JWT verification, are the only valid identity source.
- Reading a DynamoDB numeric straight into `json.dumps()` without casting
  `Decimal` → `int`/`float` throws at runtime, not at review time.

## 2. Edit two places or it half-works

- `JWT_SECRET` must match across `Authentication`, `Proxy`, and `Authorizer`
  Lambda env vars — mismatch = silent 401 on all logins.
- Any Lambda importing `sentry_sdk` needs `python_vendor/` bundled into its
  deploy zip, or Sentry import fails at cold start.

## 3. Single-writer paths — the only legal way

- Item mutation + `InventoryTransactions` audit log write in one
  `TransactWriteItems` — never write the item without the log entry.
- Role/membership is looked up live per request via `_org.get_membership()`
  — never cached in the JWT — so a removal takes effect on the next request.
- Invite tokens: generate with `secrets.token_urlsafe(32)`, store only the
  SHA-256 hash. The raw token exists exactly once, in the invite email.

## 4. Boundaries that look like one thing and are another

- Proxy-stage vs. real-stage API Gateway: bare `/prod/*` routes require the
  backend `x-api-key` and reject direct calls (403). Only `/prod/proxy/{proxy+}`
  is reachable from the browser. Tests must target the proxy path.
- `Sessions` table looks like session storage but isn't — it's audit-trail
  and logout cleanup only. Token validity is never checked against it.

## 5. Before you finish

- New Lambda importing `sentry_sdk`? Confirm `python_vendor/` is in the zip.
- Touched auth, org headers, or role checks? Confirm `_org.has_role()` is
  enforced on the mutation, not just hidden in the UI.
- Touched an item mutation? Confirm it's inside a `TransactWriteItems` with
  the transaction log, and that `version`/`If-Match` optimistic locking is
  respected.
