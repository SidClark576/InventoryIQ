# PRD: Panindo (formerly InventoryIQ): Mobile Launch on Google Play (Android first)

> Status: Decided (grilled + gap review) · Owner: Sidney · Created: 2026-10-11 · Updated: 2026-10-12
> Readiness checklist (what the current app is missing before the mobile build): [PRD-mobile-readiness.md](PRD-mobile-readiness.md)
> Domains: `panindo.app` = marketing + legal site (`site/`) · `app.panindo.app` = web app, invite/reset links, deep-link files

## TL;DR

Rebrand InventoryIQ as **Panindo** and launch it on **Android (Google Play)** first for small stores: sari-sari stores, convenience stores, and shops. Launch markets are the **US and the Philippines**. The app packages the existing React web app and adds native barcode scanning, push alerts for low stock, and stock counts that keep working without signal. A free plan gets a store started. Pro and Business plans, bought in-app through Google Play, unlock more items, more seats, and insights. Backend spending stays near $0 until paying customers justify more.

## Platform scope: Android first (decided 2026-10-12)

- **v1 ships on Android (Google Play) plus the existing web app.** There is no iOS app at launch.
- **Why:** most of the Philippine market uses Android, and the sari-sari audience overwhelmingly so. Google's fee is $25 once instead of Apple's $99 a year, which fits the near-$0 spend rule. Billing and sign-in cover one store instead of two, and Google's 12-tester, 14-day test can start sooner.
- **iPhone users** can use the web app at `app.panindo.app`, with the same account and store. The marketing site says only "Coming soon to Google Play".
- **Deferred to Phase 6 (iOS):**
  - Sign in with Apple
  - StoreKit 2 and App Store Server Notifications
  - APNs push
  - the iOS privacy manifest and Xcode build floor
  - TestFlight
  - Apple developer enrollment and the Small Business Program
  - the App Store privacy label and EULA clauses
  - Apple "Hide My Email" invite handling

  Apple-specific lines elsewhere in this PRD are kept for Phase 6 and marked **(iOS, Phase 6)**. They aren't v1 scope.
- **When to start iOS:** open question O1 below. Until then, the Apple Developer fee is not paid.

## Background

- The product today is a web app. Users sign up, add items, log stock in/out with a full audit trail, and get low-stock insights.
- **Orgs and roles are built but not live.** The Owner/Admin/Editor/Viewer code exists in the repo, but its Lambdas, tables, and the org index were never deployed. Production is single-user today (see `docs/aws-live-inventory.md`).
- There is no billing and no store presence. Alerts go out by email. A sign-in lasts 8 hours and can't be refreshed. Barcode support is a lookup, not a camera scanner.
- All infrastructure was created by hand. There is no infrastructure-as-code and only one environment (production).
- The restructure is already in progress: the frontend is now a single React app, and the Suppliers and Forecast features are gone. This PRD builds on that base.

## Problem & Target Users

- **Who:** owners of small stores and their 1–10 staff who count and receive stock. That means sari-sari stores and small groceries in the Philippines, and convenience stores and small shops in the US.
- **Pain:** stock is counted and received away from a desk. Counts end up on paper or in phone notes and get typed in later, or never. Low-stock warnings go to email, where nobody sees them in time.
- **Discovery gap:** store owners look for tools in the App Store and Play Store, and we aren't there.
- **Impact:** stock data goes stale, stores run out of things, and the product can't grow beyond people invited by hand.

## Goals & Success Metrics

| Goal | Metric | Launch target |
|---|---|---|
| Approved on Google Play | Review cycles to production approval | ≤2 |
| Self-serve activation | % of new signups adding ≥5 items within 7 days | ≥40% |
| Mobile earns its place | % of stock adjustments made from mobile | ≥50% by day 60 |
| Fast floor workflow | Median time from scan to stock adjusted | ≤10 s |
| Revenue = traction | Free → paid conversion among orgs active 30+ days | ≥4% |
| Retention | Org-level day-30 retention | ≥30% |
| Quality | Crash-free sessions · store rating | ≥99.5% · ≥4.5★ |
| Offline is trustworthy | Queued changes that sync on the next app open, with no user action | ≥99% |
| Lean backend | Monthly AWS bill before paid customers | ≤$10 |

## Solution Overview

1. **One product, two surfaces at launch.** Android and web share the same account, org, inventory, roles, and plan. iOS joins later (Phase 6).
2. **Packaged React app.** Capacitor wraps the existing React app. Barcode scanning, push alerts, offline mode, and haptics are native. They are the core of the product, and they also answer Apple's "repackaged website" rule (Guideline 4.2).
3. **Built for the store floor.** Scan → find item → adjust stock in 3 taps or fewer. Receiving a delivery and counting stock are the two flows to make excellent.
4. **Freemium with store billing.** Every mobile feature is free. Customers pay when they grow (more items, more seats, insights).
5. **Lean, AWS-native backend.** Infrastructure is defined in AWS SAM. DynamoDB stays. Cognito handles sign-in. Paid infrastructure is added only when revenue covers it 3×.

## User Experience

**New store finds Panindo on Google Play**
1. The owner installs the app and signs up with Google or email.
2. They name the store. This creates their org, with them as Owner.
3. They add items: scan a barcode (the name is prefilled when the barcode is known), type them in, or import a spreadsheet on the web.
4. The app asks for push permission and explains why ("Get warned before you run out").
5. The owner verifies their email and invites a teammate. The invite link opens the app if it's installed, or Google Play if not.

**Receiving a delivery (core flow)**
1. The user taps **Scan**, which sits in the center of the bottom navigation.
2. They scan a box. The item opens with large **+ / −** controls.
3. They enter the quantity and confirm. A haptic tick and a toast confirm it, and the scanner reopens.
4. An unknown barcode opens "Add new item" with the barcode prefilled. This needs Editor or above; Viewers see "not found".

**Counting stock with no signal**
1. A banner shows "Offline: changes will sync" and how many changes are pending.
2. **Adjustments** (+5, −2) queue normally.
3. **Counts** ("there are 40") record an exact number. On sync, if anyone changed that item since this device last synced, the counter sees a prompt: "Ben added 10 after your count. Keep 40 or use 50?" A count never overwrites silently.
4. Changes sync **while the app is open**: when the connection returns, or the next time the app is opened. Neither iOS nor Android reliably runs sync in the background, so background sync is opportunistic only.
5. A change that can't apply (item deleted, access removed) goes to "Needs attention" with the reason, plus Retry and Discard. It is never dropped silently.

**Low-stock alert**
- Push: "Paper cups: 12 left (threshold 50)". Tapping it opens the item. Alerts are opt-in per user, per org.
- If push permission is denied, alerts still appear in an in-app alert list. Users can opt in to email alerts, sent individually to them. Shared alert topics are not used (see R10.1).

**Upgrading**
- When a store hits a Free limit, a paywall explains what Pro unlocks and offers a 14-day free trial. Purchase goes through the native Google Play sheet. The plan applies to the whole org on every device. Only the Owner can buy.
- The web app shows the plan but doesn't sell it. Web upgrade prompts say "upgrade in the Panindo app".

**Navigation**
- Bottom tabs match the web app's navigation: **Today**, **Stock**, **Scan**, **Activity**, **More** (Team, insights, account, plan). The org switcher is in the header.

## Requirements

### R1. Accounts & sign-in (Amazon Cognito, Essentials tier)
- Sign in with email and password, or **Google**. **Sign in with Apple (iOS, Phase 6)** becomes required once an iOS app offers Google sign-in (Apple 4.8).
- Sign-in runs in the system browser and returns through a deep link (PKCE). Google blocks sign-in inside embedded web views.
- **Email verification** is required before inviting teammates or upgrading. Google sign-ins count as verified.
- Users stay signed in for **30 days**, renewed while the app is in use. Tokens live in the device's secure storage.
- **"Sign out of all devices"** is in Account settings and takes effect within **15 minutes** (access tokens last 15 minutes). A password change also signs out every device.
- Removing a member from an org is **instant**, because membership is checked live on every request.
- **In-app account deletion** plus a public web page where users can request deletion (Google Play requirement; Apple 5.1.1(v) also requires in-app deletion for Phase 6). A sole Owner of an org with other members must transfer ownership or delete the org first.
- Existing users move to Cognito **on their first sign-in, keeping their passwords** (Cognito's user-migration trigger checks the old password once).
- Auth emails go through Amazon SES. Cognito's built-in email is capped at 50 per day.

### R2. Core mobile features
- Camera scanning of EAN-13, UPC-A, Code 128, and QR, with a torch toggle.
- Stock in/out from the item screen and straight from a scan, with large tap targets and haptics.
- Push notifications: low stock (opt-in per user per org), invite accepted, role changed, and access removed. Email alerts remain available.
- Search, category filter, and item detail with that item's audit history.
- Org switcher. Team management (invite, change role, remove) for Admin and above.
- Role permissions are unchanged on mobile, and the server enforces them on every request.

### R3. Offline
- The last-synced inventory for the current org is viewable offline.
- Stock adjustments queue offline and sync as deltas (+N/−N).
- Counts sync as an exact number, with the conflict prompt described above. Only Editors and above can count. Counts appear in the activity log as their own type ("Count: 40, was 38").
- Each queued change applies exactly once, even after retries or a crash.
- Creating, editing, or deleting items requires a connection in v1, and those controls show as disabled while offline.
- The queue is stored in native SQLite, not web storage, because iOS can erase web-view localStorage and IndexedDB under storage pressure.
- Each queued change is tagged with its org. Switching orgs offline never mixes queues.
- A change older than 7 days that hasn't synced moves to "Needs attention" instead of being sent automatically.
- The device time is kept as "counted at" for the record. Server time decides ordering and conflicts, so a wrong phone clock can't corrupt history.

### R4. Plans & billing (in v1)

| | Free | Pro | Business |
|---|---|---|---|
| Items | 100 | Unlimited | Unlimited |
| Seats (every member counts, Viewers included) | 2 | 5 | 25 |
| Scan, push, offline, CSV import & export | ✅ | ✅ | ✅ |
| Insights | — | ✅ | ✅ |
| US | $0 | $9.99/mo · $99/yr | $29.99/mo · $299/yr |
| Philippines | ₱0 | ₱199/mo · ₱1,990/yr | ₱599/mo · ₱5,990/yr |

- Purchases go through **Google Play Billing only** (StoreKit joins in Phase 6). There is no web checkout at launch. Plans are monthly or annual auto-renewing subscriptions. Restore Purchases is supported.
- The plan belongs to the **org**. Only the Owner buys it. A plan bought on Android is active on the web too, and later on iOS.
- A **14-day Pro free trial** runs through the store's free-trial offer, once per org.
- Each person can **own one Free org**. They can join any number of orgs as a member.
- **Limits are enforced on the server.** An org over its limit becomes read-only for new items and seats, and nothing is deleted.
- **A CSV import that would exceed the limit is blocked** with a preview before anything is written, and the message "upgrade or start a trial in the app". A file is never half-imported.
- **Ownership transfer:** the original buyer's subscription keeps running, and the plan screen shows "Billed via [name]'s Google account". The new Owner is prompted to subscribe before the period ends. If nobody renews, the org drops to Free under the rules above.
- **Existing orgs** get Pro free for 12 months, with an in-app notice 30 days before it ends.
- A grace period on failed renewals, matching the store defaults.

### R5. Brand & store readiness
- The name is **Panindo** everywhere: stores, the web at **panindo.app**, emails, sender name, legal pages, code, and AWS resource names. The old Netlify URL redirects to the new address.
- Store listing: "Panindo: Stock & Barcode Tracker". The app is English-only. The Philippine listing has Filipino and English text and screenshots with peso prices.
- **Name clearance (do it yourself):** USPTO is clean. Before committing: check IPOPHL by hand, check a .ph domain, and register **panindo.app** right away (it is not reserved). Social handles use @panindoapp, because @panindo is taken on TikTok. Filing a trademark and getting an attorney review wait until traction.
- The app is built for Android phones (Android 7+). Tablets run it unoptimized. Tablet layouts come in v1.1.
- Developer accounts are enrolled **as an individual** (there is no registered business yet).
  - (iOS, Phase 6) Apple: the seller name shown is the developer's legal name. Apply for the Small Business Program (15% commission); confirm it covers subscriptions.
  - Google: requires a closed test with ≥12 testers for ≥14 days before production. Use the beta businesses as testers, and start the clock early.
- The Google Play address is shown publicly for monetized apps. Use a PhilPost P.O. box, with the home address as the fallback if Google rejects the P.O. box.
- (iOS, Phase 6) Apple's EU trader declaration: declare "not a trader". There is no EU distribution, so nothing is displayed.
- Privacy policy (covering the PH Data Privacy Act and US state laws), terms of service, and a support URL.
- Google Play Data safety form (and the App Store privacy label in Phase 6): email, usage data, crash data (Sentry), and purchases.
- A demo account with sample inventory for App Review.
- Export compliance: standard HTTPS only. The Android build targets the API level Google Play currently requires.

### R6. Infrastructure & cost
- **AWS SAM (YAML)** defines everything. The same template deploys **panindo-staging** and **panindo-prod** in the existing AWS account, in **us-east-1**.
- **DynamoDB stays** at launch (≈$0 under the always-free tier). Aurora is deferred until the spend rule below is met. When it is, use Aurora PostgreSQL with Data API and no RDS Proxy.
- **Spend rule:** a paid infrastructure upgrade turns on only when monthly subscription revenue is ≥3× its monthly cost. This covers Aurora (≈$44/mo), a separate staging account, paid auth tiers, and a trademark filing. An AWS budget alarm fires at **$10/month**.
- Known unavoidable costs: Google $25 one-time and panindo.app about $15/yr. Apple's $99/yr starts only with Phase 6.
- **Staging** gets beta builds and Playwright runs, and holds only fake sample data.

### R7. Migration & switchover (Phase 0)
- Build a fresh Panindo stack. One script copies all data and **creates each user's personal org in the same pass** (the logic from `migrate_orgs.py`). This makes orgs live at the same time.
- **Rehearse the full migration on staging at least twice** against a copy of production. Production switchover happens only after a clean rehearsal with matching row counts.
- The switchover itself is a single short read-only window. The old InventoryIQ stack stays read-only for 30 days as a rollback path, then gets deleted.
- What users notice:
  - Everyone signs in once more, with the same password.
  - Email alerts restart as per-user emails sent through SES. There is no subscription to re-confirm. Alert emails were paused on 2026-10-12, when the shared-topic subscription was removed (R10.1).
  - The old URL redirects.
  - Users get an email 3 days ahead, and the app shows a banner.

### R8. Quality, troubleshooting & operations
- **Troubleshooting:**
  - Query data in the DynamoDB console with PartiQL.
  - A request ID follows every request through API Gateway, Lambda logs, and Sentry.
  - Keep saved CloudWatch Logs Insights queries (for example, "errors for user X in the last hour").
  - Reproduce bugs on staging.
- Sentry runs on both apps (`@sentry/capacitor`) and on the backend. The frontend has no Sentry today.
- **PostHog** (free tier, 1M events/month) records analytics events for every metric above, with no personal data in event properties. The frontend has no analytics today.
- Accessibility basics:
  - Light and dark themes follow the system setting.
  - Dynamic Type is supported.
  - Every control has a screen-reader label.
  - Tap targets are at least 44pt.
- A forced-update screen for app versions the backend no longer supports.
- Per-org request quotas by plan.

### R9. Support
- A support email plus a help page at launch. Paid plans get a reply within 1 business day. Free plans get best effort. No in-app chat in v1.

### R10. Platform & architecture gaps (verified against code and platform docs, 2026-10-12)

Each gap below names what exists today and what launch needs.

**10.1 Security & abuse (Phase 0)**
- **Alert leak (hotfixed 2026-10-12):** `LowItemInsight` and `DailyAlert` published every user's alerts to one shared SNS topic with no filter, and signup and login subscribed users to it. Any confirmed subscriber would have received every user's stock alerts. The topic had 0 subscribers, so nothing leaked. The subscribe calls are now removed from `Authentication.mjs`. **Replacement:** per-user delivery only. Push goes to the user's own devices, email goes to the user alone through SES, and nothing is shared.
- **Per-org rate limits:** the proxy sends one API key for all users, and the live usage plan allows 10,000 requests per day, shared by everyone, with no throttle. Launch needs per-org and per-user limits by plan, enforced server-side, so one store or bot can't lock out everyone.
- **Barcode lookup limits:** the UPCItemDB *trial* tier is used, and unknown barcodes aren't cached. Launch needs: cache misses for 7 days, a per-org daily lookup quota, and lookup in the org's own items first. Expect weak coverage for Philippine products.

**10.2 Account deletion (Phase 0, both stores)**
- No delete endpoint or UI exists today. `CascadeDeleteUser` covers items, transactions, sessions, and auth records, but **not** orgs, memberships, or invites.
- Launch needs in-app deletion plus a public web deletion page (its URL goes in Google's Data safety form). Deletion removes the Cognito user, push device tokens, memberships, and invites. It blocks a sole Owner of an org with other members (they transfer ownership first).
- Before deleting, warn users with an active subscription that they must cancel it in Google Play, because the store keeps charging otherwise.

**10.3 Subscription backend (Phase 2)**
- Nothing exists today. Launch needs:
  - An org entitlement record (plan, source store, original buyer, expiry, state).
  - (iOS, Phase 6) An App Store Server Notifications V2 endpoint, plus the App Store Server API for status checks.
  - Google real-time developer notifications through Cloud Pub/Sub (within the free tier), with purchases verified via the Play Developer API.
- **Every Google purchase must be acknowledged within 3 days**, or Google refunds it automatically.
- Handle renewals, failed renewals, grace periods (3/16/28 days), billing retry for up to 60 days, refunds, and revocations.
- **One org, one subscription:** if the org already has an active plan from either store, the paywall shows "Already subscribed via App Store/Google Play" instead of selling a second subscription.
- The paywall shows each plan's title, length, and price, plus Terms and Privacy links (also Apple 3.1.2 for Phase 6), and Restore Purchases.
- The client reads plan limits (items, seats) from the server's entitlement response. Today the seat cap of 5 is hard-coded in `_org.py` and `TeamScreen.tsx`.

**10.4 Offline & sync (Phase 1)**
- Stock in/out today sends an **absolute quantity** with If-Match, and `UpdateItem` overwrites it. Queued offline changes would conflict.
- New endpoints:
  - **Adjust:** an atomic +N/−N.
  - **Count:** an exact number plus the version the device last saw. If the item has changed since, the server returns a conflict and the user resolves it.
- Duplicate protection (`Idempotency-Key`) exists only on AddItem today, and the proxy drops BulkImport's header. Launch needs it on **every write**, with keys kept for ≥7 days to cover the queue's maximum age.
- **"Changed since" sync:** the current `/items` returns the whole inventory in one response, and transactions use a full-table scan capped at 200 rows. Launch needs incremental item sync (changes since the last sync) and an index for activity per org and per item. This matters on slow Philippine connections and for unlimited inventories.

**10.5 Sessions, links & CORS (Phase 0/1)**
- Tokens, the current org, and the role live in `sessionStorage` today, which is cleared when the app closes. Mobile needs Keychain/Keystore secure storage (`@aparajita/capacitor-secure-storage`) for tokens and Capacitor Preferences for non-secret settings. The 401 handler's `login.html` redirect becomes a route change.
- **Deep links:** reset and invite links are hard-coded to the Netlify domain. `app.panindo.app` (the web app's domain, used by invite and reset links) serves `/.well-known/apple-app-site-association` and `/.well-known/assetlinks.json` over HTTPS with no redirects, and the SPA rewrite must not hide them. Android uses the **Play App Signing** SHA-256 fingerprint. Changes can take up to 7 days to re-verify on Android 15+.
- **Invites accept by token, not by email match**, which is ready for Phase 6, when Apple "Hide My Email" users sign in with a relay address.
- **CORS:** allow `capacitor://localhost` (iOS) and `https://localhost` (Android). Use one shared CORS helper; the Auth Lambda currently rejects `Idempotency-Key` and `X-IQ-Org`. Add `Access-Control-Expose-Headers: ETag`, which is missing everywhere, so cross-origin clients can't read item versions.
- **Web CSP** (`netlify.toml`): add the Cognito domains to `connect-src` and `form-action`. The app bundle gets its own CSP.

**10.6 Native capabilities (Phase 1)**
- **Barcode:** the scanner library (Quagga) loads from the jsDelivr CDN, so it fails offline and inside the app. Use the native `@capacitor-mlkit/barcode-scanning` with `startScan()`, which doesn't depend on Google Play services. Check its iOS 15.5 / CocoaPods requirement against Capacitor 8's Swift Package Manager default. The web build bundles a scanner locally instead of using the CDN.
- **Push:** a device-token table and register/unregister endpoints. Amazon SNS mobile push (APNs .p8 token auth, FCM HTTP v1, about $0.50 per million). FCM needs a Firebase project. Android 13+ requires asking for notification permission at runtime. Tokens are removed on sign-out, member removal, and account deletion.
- **Permissions:** camera permission text (`NSCameraUsageDescription`). If camera access is denied, users can type the barcode. If push is denied, the in-app alert list still works.
- **Same barcode on two items:** scanning shows a chooser.

**10.7 Build & store floor (Phase 1, re-check before Phase 3)**

| Platform | Requirement (as of 2026-10-12) |
|---|---|
| iOS (Phase 6) | Xcode 26 + iOS 26 SDK for uploads; privacy manifest (`PrivacyInfo.xcprivacy`) for the app and every plugin; Push capability; app runs on iOS 15+ (Capacitor 8 minimum) |
| Android | **Target API 36, which is already overdue (extension ends 2026-11-01)**; Play Billing Library 8 (same deadline); 16 KB memory page support for native libraries by 2027-02-01; edge-to-edge layouts handled (Capacitor SystemBars `--safe-area-inset-*` variables); app runs on Android 7+ (minSdk 24) |
| Shared | Capacitor 8.5.x, Node 22 |

**10.8 Locale (Phase 0)**
- Prices are hard-coded to USD today (`format.ts`), and dates use the device locale with no timezone.
- **Each org gets a currency (₱ or $) and a timezone**, set at signup from the device region and editable by the Owner.
- The daily summary and the Today screen use the org's timezone. The current daily alert runs at 07:00 Honolulu time but labels it UTC.

**10.9 Versioning (Phase 1)**
- No version mechanism exists today. The app sends `X-Client-Version`. Below the minimum supported version, the backend returns `426`, and the app shows the forced-update screen.

**10.10 Imports (Phase 0)**
- The import bucket doesn't exist live, and the import Lambdas aren't deployed. Define them in SAM. Use a presigned POST with a file-size limit; the current PUT has no size cap.

### R11. Edge cases

| Case | Expected behavior |
|---|---|
| Same email signs in with Google and password (Apple in Phase 6) | **One account.** A Cognito pre-sign-up hook links the federated sign-in to the existing user. Cognito does not link them by default |
| (iOS, Phase 6) Apple "Hide My Email" user is invited by their real email | The invite is accepted by token, and their account joins the org |
| (Phase 6) Owner subscribes on iOS, then tries on Android | The paywall shows "Already subscribed via App Store". No second purchase |
| Owner deletes their account with an active subscription | Warning plus cancel instructions first. Billing continues until they cancel in the store |
| Member removed while their offline changes are queued | Changes go to "Needs attention: you no longer have access" |
| Plan lapses while offline changes are queued | Stock adjustments still apply. New items and seats stay blocked |
| Phone clock is wrong | Server time orders history. The device time is kept only as "counted at" |
| Same barcode on two items | Chooser |
| Camera or push permission denied | Manual barcode entry. In-app alert list |
| Very slow or intermittent connection (rural PH) | Cached data stays visible, requests retry with timeouts, and sync is incremental |
| Huawei or other phones without Google services | **Out of scope v1.** No FCM push. Scanning still works because the scanner is bundled. Documented on the support page |

## Launch Plan

| Phase | Ships | Exit criteria |
|---|---|---|
| **0. Foundations** | Register panindo.app; IPOPHL check; Google Play developer account (individual). SAM stacks (staging and prod); Cognito with Google and email, plus account linking; email verification; account deletion (R10.2); per-org rate limits and barcode quotas (R10.1); per-user alert delivery; per-org currency and timezone (R10.8); import bucket (R10.10); CORS and CSP (R10.5); server-side plan limits; org features deployed; data migration rehearsed ×2; switchover; rename to Panindo; legal pages | Production runs on the Panindo stack. Orgs are live. Users have migrated with no data loss. No shared alert channel. AWS ≤$10/mo |
| **1. Mobile MVP** | Capacitor 8 Android build that meets the R10.7 Android build floor; bottom-tab navigation; native ML Kit scanning; push (SNS + device tokens); deep links (apple-app-site-association / assetlinks); secure token storage; adjust and count endpoints; idempotency on every write; SQLite offline queue; incremental sync; client version gate; Sentry and PostHog; Cognito sign-in through the system browser | The team does real counts for 1 week with no data loss. Duplicate-account and Hide My Email cases tested |
| **2. Monetization** | Plans, paywall with the required terms, trial, Play Billing Library 8, the R10.3 entitlement backend (Google notifications via Pub/Sub, purchase acknowledgement), designed store-agnostic for iOS later, one-subscription-per-org guard, Restore Purchases | Test purchase is active on Android and web. Refund revokes access. Lapse makes the org read-only with no data loss. Every Google purchase is acknowledged in under 3 days |
| **3. Beta** | Play closed test with 12–20 real stores (US and PH) for ≥14 days. Store listings, screenshots, and forms | Crash-free ≥99.5%. Top issues fixed. Google production access granted |
| **4. Launch** | Submit to both stores. Phased rollout | Approved on both. Metrics dashboard live |
| **5. v1.1** | Tablet layouts, shared-device mode, biometric unlock, offline item editing, low-stock widget | Driven by launch metrics |
| **6. iOS** | Apple Developer enrollment; Sign in with Apple; StoreKit 2 + App Store Server Notifications V2; APNs; iOS build floor (Xcode 26, privacy manifest); TestFlight beta; App Store listing and privacy label; EULA clauses on the site | Starts when O1's trigger is met |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| (Phase 6) Apple rejects it as a "repackaged website" (4.2) | Med | Native scanning, push, offline, haptics, and navigation that feels native |
| Cognito sign-in inside Capacitor (no official guide; Amplify reportedly breaks with deep links) | Med | Hand-built system-browser + deep-link PKCE flow. Prove it first in Phase 1 |
| Big-bang Phase 0 switchover (rename + SAM + Cognito + orgs at once) | Med | Two clean rehearsals, matching row counts, old stack read-only for 30 days for rollback |
| Offline double-counts or lost changes | Med | Delta adjustments, count conflict prompt, exactly-once sync, "Needs attention" list, two-device tests |
| Android back button closes the app or returns to login instead of closing sheets and dialogs | Med | Back-button handling in the readiness PRD (E18) |
| Low-end Android phones (2–3 GB RAM, old WebView) are slow | Med | Test on a low-end device. Keep the JS budget under 300 KB |
| IAP rejection | Low | All upgrades go through store billing. No links to outside payment |
| Android target API 36 deadline (extension ends 2026-11-01) passes before launch | Certain | Build on Capacitor 8 (target 36) from day one. New apps must meet the current target at submission |
| Shared 10,000/day API quota exhausted by one user after public signup | High (until fixed) | Per-org and per-user limits in Phase 0 (R10.1) |
| Duplicate accounts when the same email uses Google, Apple, and password | Med | Cognito pre-sign-up account linking (R11) |
| Google purchase not acknowledged within 3 days, so it's auto-refunded | Med | Server acknowledges on verification. Alarm on unacknowledged purchases |
| Barcode lookup rate limits and poor coverage of Philippine products | Med | Cache misses, per-org quota, org's own items first, manual entry |
| **Selling without a registered business** (PH income tax registration, BIR penalties) | Med | Accepted at launch. Revisit before the first Google Play payout |
| Google Play shows the developer's address publicly | High | PhilPost P.O. box first, home address as fallback |
| Name conflict found later in the Philippines (IPOPHL unverified) | Low–Med | Manual IPOPHL check before announcing. File the trademark after traction |
| Public signup spam or cost spikes | Med | Email verification, plan quotas, existing rate limits, $10 budget alarm |
| Store commission (15–30%) | Certain | Prices assume the 15% small-business rate |

## Out of Scope (v1)

- A native rewrite (React Native, Swift, or Kotlin).
- Aurora or RDS (deferred by the spend rule).
- Web checkout, Stripe, RevenueCat.
- Shared-device mode, tablet layouts, widgets, Apple Watch.
- Offline item create, edit, or delete.
- CSV import and printed reports in the mobile app (both stay on the web; CSV import is still free).
- Bluetooth or hardware scanners, label printing.
- Multi-location stock, suppliers, purchase orders, forecasting, accounting sync.
- Markets beyond the US and Philippines. Languages other than English inside the app.

## Open Questions

| # | Question | Recommendation |
|---|---|---|
| O1 | When does the iOS phase start? | When **10 orgs are paying** or **≥25% of active web users are on iPhone**, whichever comes first |
| O2 | What does an iPhone-only Owner see when they hit a plan limit on the web? | "Upgrade from the Panindo Android app. iPhone app coming soon." No web checkout. Demand from US iPhone owners is a signal to start O1 sooner |

## Decision Log (grilling, 2026-10-11 → 2026-10-12)

| Topic | Decision | Rejected |
|---|---|---|
| Audience | Small stores with teams; US + PH | Individuals first |
| Name | Panindo | InventoryIQ (live USPTO mark + same-name Play app), Tindaq (crowded with "Tinda" POS apps), Restoq (existing RESTOQ app; .com/.app taken) |
| Build | Capacitor wrap | React Native rewrite |
| Database | DynamoDB until revenue covers Aurora 3× | Aurora now (≈$44/mo, or 15–30 s cold starts if scaled to zero) |
| Auth | Amazon Cognito Essentials | Clerk (7-day sessions on the free tier; custom roles $100/mo; no Capacitor SDK; can't import Node scrypt hashes, forcing password resets), keeping the in-house JWT |
| IaC | AWS SAM, staging + prod, same account, us-east-1 | Importing hand-made resources; ap-southeast-1 |
| Billing | In-app only, org-level, 14-day trial | Stripe on web, RevenueCat |
| Business entity | Individual developer accounts; launch unregistered (risk noted) | Register before launch |
| Alert leak (2026-10-12) | Removed shared-topic subscriptions now; per-user push and SES email later | Waiting for Phase 0 |
| Locale | Per-org currency (₱/$) and timezone, set at signup | Fixed USD and UTC |
| Analytics | PostHog free tier + Sentry | None, or paid analytics |
| Platform | Android (Google Play) + web first; iOS in Phase 6 | iOS + Android at once |
| Marketing copy | "Coming soon to Google Play" | Mentioning iPhone or the web app |

## Engineering Notes (for the follow-up design doc)

- Retire AGENTS.md's "stdlib-only JWT" rule when Cognito ships. API Gateway's native Cognito authorizer replaces the JWT checks in Proxy and Authorizer. The live org-membership lookup and header injection stay.
- CORS, session storage, adjust and count endpoints, idempotency, push, deep links, and the build floor are specified in **R10**, with code evidence.
- `Authentication.mjs` no longer subscribes users to the shared SNS alert topic (hotfix, 2026-10-12). The topic and its publishers (`LowItemInsight`, `DailyAlert`) are retired in the Panindo stack.
