# PRD — InventoryIQ

> Product Requirements Document. What InventoryIQ is, who it is for,
> what it does today, and what it does not do yet.
> For *how* it is built, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. TL;DR

InventoryIQ is a multi-tenant inventory management web app: teams track
stock levels, log stock in/out, get low-stock and reorder alerts, forecast
stockouts, and manage suppliers, with organization-level roles so multiple
users can share and control access to the same inventory.

## 2. Background

Small teams tracking inventory in spreadsheets lose visibility into stock
levels, reorder timing, and who changed what. InventoryIQ replaces that with
a shared, audited, role-gated system: every quantity change is logged, every
user's access is scoped to their organization, and low-stock/forecast
signals surface before a stockout happens.

## 3. Problem & Target Users

- **Primary user:** an inventory/ops person managing physical stock (retail,
  small warehouse, restaurant supply) who needs to see current levels, log
  changes, and get warned before running out.
- **Secondary users:** teammates with narrower roles (viewer/editor) who need
  to see or update stock without full admin control; an org owner who manages
  membership and billing-adjacent seat limits.
- **Non-users:** organizations needing barcode-scale warehouse robotics,
  ERP-grade accounting integration, or multi-currency/multi-warehouse
  logistics — out of scope today.

## 4. Goals & Success Metrics

| Goal | Measure |
|---|---|
| Prevent stockouts | Forecast/low-stock alerts fire before quantity hits threshold — not instrumented as a tracked metric today |
| Multi-user org access without leaking data across tenants | Every read/write scoped by `orgID`; role removal takes effect instantly (live membership lookup) |
| Auditable inventory changes | Every mutation writes to `InventoryTransactions` in the same transaction |
| Fast onboarding for a new org | Seat cap (`ORG_SEAT_CAP`, default 5) — not currently tunable per-org in the UI |

## 5. Solution Overview

1. **Auth & tenancy** — stateless JWT login, org membership + role
   determine what a user can see and do.
2. **Inventory core** — add/edit/search items, adjust stock with an audit
   log, soft-delete with 30-day restore window.
3. **Insight layer** — low-stock detection, reorder recommendations,
   stockout forecasting from historical stock-out logs.
4. **Supporting ops** — supplier records, CSV bulk import, barcode lookup,
   printable reports, scheduled daily alert summaries.

## 6. User Experience — what exists today

- **Login / signup** (`login.html`) — register, sign in, subscribe to SNS
  alerts. `forgot-password.html`/`reset-password.html` handle a time-limited
  email reset flow.
- **Dashboard** (`dashboard.html`) — KPI counts, audit log, status charts.
- **Inventory** (`inventory.html`) — paginated search, +/− stock modals,
  category filters, CSV export, print-friendly reports.
- **Add/Edit item** (`add-item.html`) — create or edit an item; edit path
  reads the item from `sessionStorage.iq_editItem`.
- **Insights** (`insights.html`) — low-stock analysis and reorder
  recommendations.
- **Forecast** (`forecast.html`) — stockout projections: daily burn rate,
  days-until-stockout, confidence, weighted by 30/60/90-day stock-out history
  (50%/30%/20%).
- **Suppliers** (`suppliers.html`) — supplier CRUD and item association.
- **Transactions** (`transactions.html`) — filtered audit log viewer.

## 7. Requirements

### 7.1 Shipped — acceptance criteria met today

- A user can register, log in, and get a stateless JWT session.
- An org owner can invite, remove, and change the role of members; removal
  takes effect on the member's next request (no token cache to expire).
- Items support create, paginated search, stock +/-, edit with optimistic
  locking (`If-Match`/`version`), soft-delete, and restore within 30 days.
- Every item mutation writes an `InventoryTransactions` audit entry in the
  same transaction as the item write.
- Low-stock and forecast pages compute from real transaction history, not
  static thresholds alone.
- CSV bulk import runs via S3 presigned URLs, with an async path for large
  files (`BulkImportAsync.py`).
- Deleting a user cascades deletion across all their owned data via
  DynamoDB Streams (`CascadeDeleteUser`).

### 7.2 Known gaps — verified in the shipped product

| Gap | Impact |
|---|---|
| No unit test suite, only E2E against live AWS | A logic bug in a Lambda not covered by an E2E path ships undetected |
| `ORG_SEAT_CAP` is a fixed default (5), not per-org configurable in UI | Growing orgs must be raised by a backend change, not self-serve |
| Weekly `cerebrum-reflection` cron (dev tooling, not product) can hang indefinitely (`ETIMEDOUT`) without pruning | Not a product gap, but a known dev-tooling reliability issue — see `.wolf/OPENWOLF.md` |

## 8. Out of Scope

- Multi-warehouse / multi-location stock tracking.
- Barcode-scanner hardware integration beyond `BarcodeLookup.py`'s lookup API.
- Accounting/ERP sync, invoicing, payments.
- Any JWT library dependency — auth stays stdlib-only by design (see
  `AGENTS.md` §4.A.1).

## 9. Open Questions

1. Should `ORG_SEAT_CAP` become configurable per organization?
2. Is a unit-test layer planned to supplement the Playwright-only E2E
   strategy, or is E2E-only intentional going forward?
3. What triggers the daily SNS alert threshold — is it per-item
   `lowStockThreshold` only, or does forecast confidence factor in?

## 10. Assumptions

| Assumption | Confidence |
|---|---|
| Product is B2B/internal-tool facing, not consumer | High |
| Single currency, no localization requirement today | Medium — not contradicted by any file, but not explicitly confirmed |
| Dark-only theme is a deliberate product decision, not a placeholder | High — stated explicitly in `AGENTS.md` §4.C |
