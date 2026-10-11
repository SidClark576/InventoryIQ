# PRD: InventoryIQ Mobile — Public Launch on App Store & Google Play

> Status: Draft · Mode: Thorough (1 interview round) · Owner: Sidney · Date: 2026-10-11

## TL;DR

Ship InventoryIQ as a free-to-download iOS and Android app that any small business can find in the stores, sign up for, and use the same day. The app wraps the existing React web app and adds what makes inventory work on a phone: camera barcode scanning, push low-stock alerts, and stock counts that keep working without signal. A free tier gets teams started. Paid plans, bought through Apple or Google, unlock bigger inventories and teams. Web and mobile share one account and one inventory.

## Background

- InventoryIQ today is a web app: sign up, create items, log stock in/out with a full audit trail, get low-stock insights, and share one inventory with teammates through orgs and roles (Owner, Admin, Editor, Viewer).
- Accounts are invite-driven and free. There is no billing, no plan limits beyond a fixed 5-seat cap per org, and no store presence.
- Alerts arrive by email. Sessions end when the browser tab closes. Barcode support is a lookup, not a camera scanner.
- Inventory work happens on the floor, in the stockroom, and at the delivery dock. That is where a phone is, and a laptop is not.
- Restructure in flight: the frontend has moved to a single React app. The old multi-page HTML, the Suppliers feature, and the Forecast feature have been removed. This PRD builds on that new base.



## Problem & Target Users

- **Who:** Small-business operators who manage physical stock as a small team: shop owners, restaurant managers, small-warehouse leads, and the 1–10 staff who count and receive stock for them.
- **Pain:** Counting and receiving happen away from a desk. Today staff write counts on paper or in a phone note and type them in later, or skip logging altogether. Low-stock warnings land in email, where nobody sees them in time.
- **Discovery gap:** A business owner looking for an inventory app searches the App Store or Play Store. InventoryIQ is not there, so it doesn't exist for them.
- **Impact:** Stock data goes stale, stockouts happen, and the product can't grow past people who are invited by hand.



## Goals & Success Metrics


| Goal                        | Metric                                                             | Launch target (proposed)             |
| --------------------------- | ------------------------------------------------------------------ | ------------------------------------ |
| Get approved on both stores | First-submission approval, iOS and Android                         | Approved within 2 review cycles each |
| Self-serve activation       | % of new signups who add ≥5 items within 7 days                    | ≥40%                                 |
| Mobile earns its place      | % of stock adjustments made from mobile (orgs with ≥1 mobile user) | ≥50% by day 60                       |
| Fast floor workflow         | Median time from scan to stock adjusted                            | ≤10 seconds                          |
| Revenue                     | Free → paid conversion among orgs active 30+ days                  | ≥4%                                  |
| Retention                   | Org-level day-30 retention                                         | ≥30%                                 |
| Quality                     | Crash-free sessions, store rating                                  | ≥99.5% crash-free, ≥4.5★             |
| Offline is trustworthy      | Queued offline changes that sync without user action               | ≥99%                                 |




## Solution Overview

1. **One product, three surfaces.** iOS, Android, and web share the same account, org, inventory, roles, and plan. A change made on one appears on the others.
2. **Wrap the React app.** Package the existing React app as a native app with Capacitor, then add real native features on top. The goal is to get one codebase into the stores fast. The native features also answer Apple's rule against "just a website in a box" (Guideline 4.2).
3. **Mobile-first workflows.** Scan → find item → adjust stock, in 3 taps or fewer. Receiving a delivery and doing a stock count are the two flows to make excellent.
4. **Works on the warehouse floor.** Inventory and stock adjustments keep working without signal. Changes queue and sync when the connection returns.
5. **Freemium.** A free plan that is useful on its own, plus paid plans bought in-app through Apple and Google. A plan bought on any platform unlocks every platform.



## User Experience

**New business, found in the store**

1. Installs the app, opens it, and signs up with Apple, Google, or email.
2. Names the business. This creates their org, with them as Owner.
3. Adds the first items: scan a barcode (name prefilled when the barcode is known), type them in, or use "import from spreadsheet on the web".
4. Allows push notifications when the app explains why ("Get warned before you run out").
5. Invites a teammate by email. The teammate's link opens the app if it's installed, or the store if it isn't.

**Receiving a delivery (core flow)**

1. Taps **Scan** (always one tap away in the bottom navigation).
2. Scans a box. The item opens with large **+ / −** controls and a quantity field.
3. Enters the received amount and confirms. A haptic tick and toast confirm it, and the scanner reopens for the next box.
4. Unknown barcode → "Add new item" with the barcode prefilled.

**Stock count with no signal**

1. A banner shows "Offline — changes will sync" plus a count of pending changes.
2. The user scans and adjusts as normal. Pending items are marked.
3. When the connection returns, changes sync on their own. Any change that can't apply (item deleted, access removed) appears in a "Needs attention" list with a clear reason. It is never dropped silently.

**Low-stock alert**

- A push notification says "Paper cups: 12 left (threshold 50)". Tapping it opens the item with a reorder action. Each user chooses per org whether to get alerts.

**Upgrading**

- A free-plan limit (for example, items or seats) shows a paywall that explains what the plan unlocks. The purchase uses the native Apple or Google sheet. The plan applies to the whole org at once, on every device. Only the Owner can buy or manage the plan.

**Navigation**

- Bottom tabs: **Home** (dashboard), **Inventory**, **Scan** (center), **Activity** (transactions), **More** (insights, team, account, plan). Org switcher in the header.



## Requirements



### R1. Accounts & sign-in (store-mandated)

- **Sign in with Apple** on iOS, because Google sign-in is offered (Apple Guideline 4.8).
- **In-app account deletion** that deletes the account and its personal data, reachable from Account settings (Apple 5.1.1(v)). Google Play also requires a web link where users can request deletion.
- If the user is the sole Owner of an org that has other members, deletion requires them to transfer ownership or delete the org first, with a clear explanation.
- **Email verification** before a user can invite others. Public signup opens the door to abuse.
- **Stay signed in** across app restarts (proposed: 30 days, refreshed while in use). Tokens are kept in the device's secure storage. Removed members still lose access on their next request.
- Invite links and password-reset links open in the app when it is installed (universal links / app links), with web as the fallback.



### R2. Core mobile features

- Camera barcode scanning, with the common 1D formats (EAN-13, UPC-A, Code 128) and QR. Torch toggle. Works in low light.
- Scan an existing barcode → open the item. Scan an unknown barcode → prefilled "add item" form (Editor+ only; Viewers see "not found").
- Stock in/out from the item screen and straight from scan, with large tap targets and haptic confirmation.
- Push notifications for: low stock (opt-in per user per org), invite accepted, and your role changed or access removed. Email alerts continue for users who prefer email.
- Search, category filter, and item detail with the audit history for that item.
- Org switcher and team management (invite, change role, remove) for Admin+.
- The existing role permissions apply unchanged on mobile. Server-side enforcement stays the source of truth.



### R3. Offline

- The last-synced inventory for the current org is viewable offline.
- Stock in/out works offline and is queued. Each change syncs as "+N / −N", not as "set to X", so two people counting the same shelf don't overwrite each other.
- Creating, editing, or deleting an item needs a connection in v1, with a clear disabled state when offline.
- Each queued change syncs once, even after retries or a crash (no double-counting).
- Failed syncs go to "Needs attention" with a reason and a retry or discard choice.



### R4. Plans & billing

- **Free** and at least one **paid** plan. Limits are enforced on the server, not just shown in the UI. Proposed limits are in Open Questions.
- In-app purchase through StoreKit (iOS) and Google Play Billing (Android). Auto-renewing monthly and annual subscriptions. Restore Purchases.
- The plan belongs to the **org**, not to a person or a device. Bought on iOS → active on Android and web.
- Downgrade or lapse never deletes data. Over-limit orgs become read-only for new items and seats until they are back under the limit or upgrade.
- Grace period on failed renewals, matching store defaults.



### R5. Store readiness

- Apple and Google developer accounts enrolled as an **organization** (needs a D-U-N-S number). This avoids Google's rule that new personal accounts must run a 12-tester, 14-day closed test, and it shows the business name as the seller.
- Privacy policy, terms of service, and support URL, hosted on the website and linked in-app.
- App Store privacy "nutrition label" and Google Play Data safety form, filled in accurately (email, usage data, crash data via Sentry, purchase history).
- Demo account with sample inventory for App Review. App Review notes explain orgs and roles.
- Store listing: name, subtitle, keywords, screenshots for required device sizes, preview video (optional), age rating questionnaire, and export-compliance answer (standard HTTPS only).
- Android build targets the API level that Google Play currently requires.



### R6. Quality & operations

- Crash and error reporting on both apps (Sentry, matching the existing backend).
- Product analytics events for the metrics above, with no personal data in event properties.
- Light and dark themes follow the system setting. Dynamic Type / font scaling supported. Screen-reader labels on all controls. 44pt minimum tap targets.
- A forced-update screen for versions too old to talk to the backend.
- Load and cost check: API and alert volume at 10× today's traffic, with per-org request quotas set by plan.



## Launch Plan (sequenced)


| Phase                     | What ships                                                                                                                                                               | Exit criteria                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| **0. Foundations**        | Developer accounts (org + D-U-N-S), legal pages, email verification, Sign in with Apple, account deletion, persistent secure sessions, per-org plan limits on the server | All R1 items live on web; legal URLs public                                  |
| **1. Mobile MVP**         | Capacitor iOS/Android builds, bottom-tab mobile navigation, scan flows, push, deep links, offline stock queue                                                            | Internal team uses it for real counts for 1 week with no data loss           |
| **2. Monetization**       | Plans, paywall, StoreKit and Play Billing, cross-platform entitlement, Restore Purchases                                                                                 | Sandbox purchase → active on all 3 surfaces; lapse → read-only, no data loss |
| **3. Beta**               | TestFlight + Play closed testing with 10–20 real businesses; store listings and screenshots                                                                              | Crash-free ≥99.5%, top beta issues fixed, all store forms complete           |
| **4. Launch**             | Submit both stores; phased rollout on Android, phased release on iOS                                                                                                     | Approved on both; metrics dashboard live                                     |
| **5. Post-launch (v1.1)** | Biometric unlock, offline item edits, home-screen widget for low stock, iPad layout                                                                                      | Driven by launch metrics                                                     |




## Risks


| Risk                                             | Likelihood | Mitigation                                                                                                                            |
| ------------------------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Apple rejects it as a "repackaged website" (4.2) | Medium     | Native scan, push, offline, haptics, native-feeling navigation; no web-only UI patterns such as hover menus or visible browser chrome |
| IAP rejection (pointing users to a web checkout) | Medium     | All in-app upgrades go through Apple and Google. No links to outside payment unless the storefront rules allow it                     |
| Offline sync double-counts or loses changes      | Medium     | +/- changes that sync exactly once; "Needs attention" list; tests that sync two devices against each other                            |
| Public signup brings spam or cost spikes         | Medium     | Email verification, plan-based quotas, existing rate limits, cost alarms                                                              |
| Store name "InventoryIQ" is taken or confusing   | Unknown    | Check both stores and a trademark search before Phase 3                                                                               |
| Store cut (15–30%) squeezes margin               | Certain    | Price with the 15% small-business rate in mind; web purchase remains available to web signups                                         |




## Out of Scope (v1)

- A fully native rewrite (React Native or Swift/Kotlin). Revisit only if wrap performance or review blocks us.
- Creating, editing, or deleting items while offline (stock adjustments only).
- CSV bulk import and printed reports on mobile. Both stay on the web, and mobile links there.
- Bluetooth or hardware barcode scanners, label printing.
- Tablet-optimized layouts, Apple Watch, widgets (v1.1+).
- Multi-location / multi-warehouse stock, suppliers, purchase orders, forecasting, accounting sync.
- Languages other than English, and currency other than one per org.



## Open Questions

1. **Plan limits and prices.** Proposal: *Free* (1 org, 100 items, 2 seats, email alerts) · *Pro* about $15/mo (unlimited items, 5 seats, push alerts, insights, CSV import) · *Business* about $39/mo (25 seats, priority support). Confirm the numbers.
2. **Web billing.** Do web signups pay through a web checkout (for example, Stripe), or is the web free-only and billing mobile-only at launch?
3. **Existing users.** Grandfather current orgs onto a paid tier for free, or apply limits after a grace period?
4. **Launch regions.** Worldwide, or English-speaking markets first? This affects tax, pricing tiers, and the privacy laws that apply (GDPR, CCPA).
5. **Store name and brand.** Is "InventoryIQ" available on both stores, and is the trademark clear?
6. **Support.** Which channel (email, in-app chat), and what response-time promise for paid plans?
7. **iPad.** Ship an iPhone-only build that runs on iPad, or skip iPad entirely at launch?



## Assumptions


| Assumption                                                                                                         | Confidence                                       |
| ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| Target is small businesses with teams; the org and role model stays at the center                                  | High (confirmed)                                 |
| Freemium with in-app subscriptions is the business model                                                           | High (confirmed)                                 |
| Capacitor wrap of the existing React app is the build approach                                                     | High (confirmed)                                 |
| Offline needs to cover stock adjustments, not full editing                                                         | High (confirmed)                                 |
| Email verification is not enforced at signup today                                                                 | Medium — not confirmed in code during this draft |
| The current backend can serve mobile clients with only auth, CORS, and deep-link changes, with no platform rewrite | Medium                                           |
| The web app stays live as a full surface alongside mobile                                                          | High                                             |
| English-only, one currency per org is fine for v1                                                                  | Medium                                           |


