# PRD: Organizations, Membership & Role-Based Access

> Status: Draft · Mode: Thorough · Owner: Sidney · Date: 2026-06-25

## TL;DR

Today every InventoryIQ account is an island — one person, one inventory, no way to let anyone else in. This feature introduces **Organizations**: an Owner can invite teammates by email and assign them a role (Owner, Admin, Editor, Viewer) so multiple people can access one shared inventory with the right level of permission. Existing accounts become their own personal org automatically, so nothing breaks for current users.

## Background

- Current product is single-user: an account = one login = one private inventory. Items, transactions, forecasts, and insights all belong to that one person.
- There is no concept of sharing, teams, or roles. If two people in a business need to see the same stock, today they must share one password.
- Auth (login, registration, password reset, rate limiting) and email delivery already exist and are reused by this feature.

## Problem & Target Users

- **Who:** Small-business owners and operators who run inventory as a team — a shop owner plus staff, a manager plus warehouse clerks, a founder plus a bookkeeper.
- **Pain:** No safe way to give a teammate access. Password sharing is the only option — insecure, no accountability, no way to limit what each person can do or to cut off access when someone leaves.
- **Impact:** Blocks adoption by any business with more than one person. Limits the product to solo users and caps account value.

## Goals & Success Metrics

| Goal | Metric |
|------|--------|
| Let owners share inventory safely | % of active orgs with ≥2 members |
| Invites convert | % of sent invites accepted within 72h |
| Right-sized access | Distribution of roles assigned (not everyone an Owner) |
| No regression for solo users | 0 access-loss incidents during migration |
| Security | Removed members lose access immediately (verified) |

## Solution Overview

- Every account belongs to one or more **Organizations**. An organization owns the inventory; members access it through their role.
- On rollout, each existing user is silently given a **personal organization** where they are the Owner, and their current inventory moves under it. No action required from them.
- An Owner or Admin invites people by **email**. The invitee receives a tokened link, accepts it, and joins the org with the assigned role. Invites work even if the person doesn't have an account yet — accepting walks them through sign-up.
- A user can belong to **multiple organizations** (their own plus any they're invited to) and switches between them with an **org switcher** in the app.
- Access is enforced by role on every action, not just hidden in the UI.

## Roles & Permissions

| Capability | Owner | Admin | Editor | Viewer |
|---|:---:|:---:|:---:|:---:|
| View inventory, transactions, insights | ✅ | ✅ | ✅ | ✅ |
| Add / edit / delete items | ✅ | ✅ | ✅ | — |
| Invite / remove members, change roles | ✅ | ✅ | — | — |
| Rename / delete the organization | ✅ | — | — | — |
| Transfer ownership | ✅ | — | — | — |

- Exactly **one Owner** per org at a time (transferable). Admins manage people but not the org's existence.
- The core ask — "invite others to *see* my inventory" — is the **Viewer** role.

## User Experience

**Owner invites a teammate**
1. Owner opens a Members/Team area, enters an email, picks a role.
2. System sends an invite email with an accept link (valid 72h).
3. Owner sees the invite listed as "Pending" and can revoke or resend it.

**Invitee accepts**
1. Clicks the link. If they have no account, they sign up first; if they do, they log in.
2. They land in the shared inventory with their assigned role's permissions.
3. The org now appears in their org switcher.

**Switching context**
- A user who belongs to several orgs uses a switcher to change which inventory they're viewing. The app always shows one org's data at a time.

**Removing access**
- An Owner/Admin removes a member; that person loses access on their **next request** (effectively immediate). Pending invites can be revoked any time and auto-expire after 72h.

## Product Decisions Added During Review

- **Org-owned inventory:** `orgID` becomes the tenant boundary for inventory, suppliers, transactions, insights, forecasts, alerts, and imports. `userID` remains the actor/account identity, not the ownership boundary.
- **Actor attribution:** Transactions should retain who performed the action (`actorUserID`) even after a member is removed. Removal does not delete historical transactions.
- **Viewer export access:** Viewers can view dashboards and inventory in-app, but CSV export and print/download reports are Admin+ at launch.
- **Org deletion rule:** Owner can delete only a solo org with no other active members or pending invites. Otherwise they must remove/revoke access first.
- **Role-change notifications:** Send email notifications when a member's role changes or access is removed.
- **Alerts:** Stock-alert subscriptions remain per-user. Invited members opt in separately after joining an org.

## Data & API Contract

**Tenant context**
- The selected org is sent with each protected API request as `X-IQ-Org`.
- `Proxy.py` validates the session user is an active member of `X-IQ-Org`, strips any spoofed identity/org headers, and forwards trusted `x-iq-user`, `x-iq-org`, and `x-iq-role` headers.
- Backend Lambdas must authorize from trusted proxy headers only. They must not trust org, role, or user identifiers from request bodies or query params.
- Removed-member cutoff must account for the proxy's current 60-second session cache. Membership/role changes should either invalidate cached session membership or use a short membership-specific lookup that is not stale after removal.

**New records**

| Record | Key | Notes |
|---|---|---|
| `Organizations` | `orgID` | `name`, `ownerUserID`, `memberCount`, `createdAt`, `updatedAt`, optional `deletedAt` |
| `OrgMembers` | `orgID` + `userID` | `role`, `status=active`, `joinedAt`, `updatedAt`; GSI by `userID` for org switcher |
| `OrgInvites` | `inviteTokenHash` | `orgID`, normalized `email`, `role`, `status`, `invitedBy`, `expiresAt` TTL; GSIs by `orgID` and email |

**Existing records to scope by org**
- Add `orgID` to `InventoryIQ`, `InventoryTransactions`, `Suppliers`, `IdempotencyKeys`, and any stockout/alert event payloads.
- Existing `userID-index` reads need org-aware replacements or filters. The target query path should be `orgID`, not a scan by all users.
- Idempotency keys must include `orgID` in the stored key namespace so two orgs can safely reuse the same client key.

**Minimum endpoint set**

| Endpoint | Purpose | Minimum Role |
|---|---|---|
| `GET /orgs` | List orgs for current user | Active member |
| `POST /orgs/{orgID}/switch` | Validate/select org context | Active member |
| `GET /orgs/{orgID}/members` | List members and pending invites | Admin |
| `POST /orgs/{orgID}/invites` | Create invite | Admin |
| `POST /org-invites/{token}/accept` | Accept invite | Invited email |
| `POST /orgs/{orgID}/invites/{inviteID}/revoke` | Revoke pending invite | Admin |
| `PATCH /orgs/{orgID}/members/{userID}` | Change role | Admin, but Owner-only when changing Owner/Admin boundaries |
| `DELETE /orgs/{orgID}/members/{userID}` | Remove member | Admin, cannot remove current Owner |
| `PATCH /orgs/{orgID}` | Rename org | Owner |
| `POST /orgs/{orgID}/transfer-owner` | Transfer ownership | Owner |
| `DELETE /orgs/{orgID}` | Delete eligible org | Owner |

## Migration Plan

1. Create org/membership/invite storage before exposing UI.
2. For every existing user, create one personal org and one Owner membership using the normalized email.
3. Backfill `orgID` onto inventory, transactions, suppliers, idempotency records, and alert metadata.
4. Update read/write Lambdas to prefer `x-iq-org` and retain compatibility for migrated-but-old clients only during rollout.
5. Release the org switcher and team page after backend authorization is live.
6. Run a post-migration check: every active inventory item has exactly one `orgID`, every user has at least one Owner membership, and no org has zero Owners.

## Requirements (Acceptance Criteria)

1. Existing users keep full access to their inventory after migration, now as Owner of an auto-created personal org.
2. An Owner/Admin can invite by email, assign one of the four roles, and see pending/accepted/expired status.
3. Invite links expire after 72h and are single-use; revoked links stop working immediately.
4. Each role grants exactly the permissions in the table above, enforced on every server action (not just UI hiding).
5. A user in multiple orgs can switch between them; data from one org is never visible while viewing another.
6. Removing a member blocks their access on the next request; they can no longer see that org's data or appear in its switcher.
7. An organization is capped at **5 members** (including Owner) at launch; attempts to invite beyond the cap are blocked with a clear message.
8. Only an Owner can rename/delete the org or transfer ownership.
9. Users cannot create, accept, or resend invites with unnormalized duplicate emails for the same org.
10. A user removed from an org cannot regain access through a stale browser tab, cached org selection, or previous invite link.
11. All item, supplier, transaction, forecast, insight, bulk import, and barcode lookup paths are scoped to the active `orgID`.
12. Member count enforcement is atomic so concurrent invites cannot exceed the 5-member cap.

## Security & Validation Requirements

- Invite tokens are opaque random values; only a hash is stored. Tokens are single-use, expire after 72h, and are safe to resend by replacing the old token.
- Email addresses are normalized lowercase before invite, membership, and user lookups.
- A user cannot invite themselves, demote/remove the only Owner, transfer ownership to a non-member, or assign roles outside the fixed enum.
- Admins cannot change Owner-only settings, transfer ownership, delete orgs, or remove/demote the current Owner.
- All mutation paths keep existing idempotency, optimistic concurrency, soft-delete, Sentry, and transaction-log conventions.
- Frontend controls may hide forbidden actions, but server checks are the source of truth and must return `403`.

## Test Plan

- Migration check: seeded legacy user becomes Owner of a personal org and retains inventory, suppliers, and transactions.
- Isolation check: user with access to Org A cannot read or mutate Org B by changing `X-IQ-Org`.
- Role matrix check: Viewer can read but cannot export or mutate; Editor can mutate inventory but cannot manage members; Admin can manage members but cannot transfer/delete org.
- Invite lifecycle check: pending, accepted, expired, revoked, duplicate, resend, and no-account signup flows.
- Removal check: removed member loses org switcher entry and receives `403` on the next protected request.
- Concurrency check: simultaneous invites cannot exceed 5 active/pending seats.

## Out of Scope (this release)

- Billing, paid seats, or plan-gated member counts (cap is a flat 5 for now).
- Granular/custom permissions beyond the four fixed roles.
- Per-item or per-category sharing (sharing is whole-org only).
- SSO, SAML, or Google/social login.
- More than one Owner per org simultaneously.
- Cross-org consolidated reporting.

## Open Questions

- Should Admins be allowed to invite other Admins, or only Owner can grant Admin?
- Should accepted invites count toward analytics separately from active members?
- Should personal orgs be user-renamable during rollout, or hidden until the user invites someone?
- Should the 5-member cap count pending invites, active members, or both? Recommendation: both, to prevent overbooking.

## Assumptions

| Assumption | Confidence |
|---|---|
| "See inventory" maps primarily to the Viewer role | High |
| Reusing existing email delivery for invites is acceptable | High |
| 5-member cap is a temporary guardrail, not a product limit | Medium |
| Inventory and all related data (transactions, insights) move with the org as one unit | High |
| Auto-migrating solo users to a personal org is preferred over prompting them | High (user-confirmed) |
| Removed-member access cut-off "on next request" is acceptable as "immediate" | Medium |
| Org IDs are UUIDs and never user-editable | High |
| Existing session tokens remain opaque UUIDs; no JWTs are introduced | High |
