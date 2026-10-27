# PRD: Mobile Readiness: Get the App Ready to Wrap for Android (Google Play)

> Status: Draft · Owner: Sidney · Date: 2026-10-12
> **Scope: Android first.** iOS is deferred to launch PRD Phase 6, so iOS-only items are marked *(iOS, Phase 6)* and are outside the gate.
> Companion to [PRD-mobile-app-launch.md](PRD-mobile-app-launch.md). That PRD decides **what** Panindo is. This one lists **what the current app is missing** before the mobile build can start, with evidence from the code.

## TL;DR

Before the web app can be wrapped with Capacitor and submitted to Google Play, these have to be fixed:

- **Security gaps**: a shared quota for all users, duplicate writes, and a user deletion that removes other people's data.
- **Data that's saved without its org.**
- **An API a phone client can't depend on**: inconsistent errors, no incremental sync, stock saved as totals instead of +/−.
- **Screens that misbehave inside a phone app**: login unreachable, sideways scrolling, broken export and print.
- **No staging, no IaC, broken CI.**

This document lists **92 checks across 10 areas**:

| Status | Count |
|---|---|
| ✅ Ready | 10 |
| 🟡 Partial | 27 |
| 🔴 Missing or broken | 55 |

The **51 P0 items** form the gate: when all of them are done, the app is "ready to wrap". About two-thirds are small (a day or less). The large ones are the AWS SAM template, Cognito, backend tests, and the incremental-sync, adjust, and count API work.

## How to read this

| Mark | Meaning |
|---|---|
| ✅ Ready | Works today and is fine for mobile |
| 🟡 Partial | Exists but needs changes, or is in progress |
| 🔴 Missing | Not built, broken, or not done yet |
| **P0** | Must be done before the mobile build starts (the readiness gate) |
| **P1** | Needed before the beta (Phase 3 in the launch PRD) |
| **P2** | Needed before public launch |
| **S / M / L** | Small (≤1 day) · Medium (2–5 days) · Large (1–2+ weeks) |
| **Owner** | **Eng** = code work · **You** = accounts, money, legal, decisions |

Every finding came from reading the code, or from running the app at phone size with Playwright (WebKit 375×812, Chromium 360×740). File references point to the evidence. Audit screenshots are in the session scratchpad (`ui-audit/`).

## Readiness scorecard

| # | Area | Checks | ✅ | 🟡 | 🔴 | Blocks the mobile build? |
|---|---|---|---|---|---|---|
| A | Security & data safety | 13 | 1 | 6 | 6 | **Yes**: quota, duplicates, deletion |
| B | Data correctness & org scoping | 7 | 0 | 3 | 4 | **Yes**: changes vanish from org views |
| C | API contract for a phone client | 8 | 0 | 2 | 6 | **Yes**: offline sync impossible as built |
| D | Accounts & sign-in | 7 | 0 | 1 | 6 | **Yes**: login unreachable in the app |
| E | Screens on a phone | 19 | 5 | 5 | 9 | Partly (back button, layout) |
| F | Native capabilities prep | 8 | 0 | 1 | 7 | Yes, for scan, links, and push |
| G | Plans & billing prep | 5 | 0 | 1 | 4 | Server limits only (P0) |
| H | Infrastructure & environments | 9 | 1 | 2 | 6 | **Yes**: no staging, no IaC |
| I | Quality, testing & observability | 10 | 3 | 3 | 4 | **Yes**: CI broken |
| J | Brand, legal & store assets | 6 | 0 | 3 | 3 | No (owner tasks) |
| | **Total** | **92** | **10** | **27** | **55** | |

---

## A. Security & data safety

*Why it matters:* a public app store listing brings strangers and bots. These gaps are acceptable for a private tool and dangerous for a public one.

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| A1 | Alerts go only to their owner | 🟡 Fixed in code, **not deployed** | Subscribe calls removed from `Authentication.mjs` on 2026-10-12 | Hotfix deployed. Shared topic retired in the new stack | P0 | S | **You** (deploy) |
| A2 | One user can't exhaust everyone's quota | 🔴 | One API key for all users. The live plan allows 10,000/day, shared by everyone (`Proxy.py:189`) | Per-user and per-org limits enforced server-side. A 429 tells the user when to retry | P0 | M | Eng |
| A3 | A failed save is never applied twice | 🔴 | Proxy re-sends POST/PUT on 5xx or timeout (`Proxy.py:211-235`) | Proxy never retries writes, or retries only with an idempotency key | P0 | S | Eng |
| A4 | Every write is duplicate-proof | 🟡 | Only AddItem uses `Idempotency-Key`. Its replay runs **before** the auth check, and keys aren't scoped per user (`AddItem.py:73-83`). Proxy drops BulkImport's header (`Proxy.py:201`) | Every write accepts a key scoped per user and org, checked after auth, kept ≥7 days | P0 | M | Eng |
| A5 | Signing out actually ends access | 🔴 | Logout and password reset delete only the audit row. The token keeps working for up to 8 hours (`Proxy.py:143-154`) | Cognito tokens (15-min access) with global sign-out (launch PRD R1) | P0 | M | Eng |
| A6 | Membership check fails closed | 🔴 | `_org.py:74-75` grants **owner** if the OrgMembers table is missing | A missing or erroring membership check returns 403, never a role | P0 | S | Eng |
| A7 | Deleting a user removes only *their* data | 🔴 | `CascadeDeleteUser.py:33-48` deletes every item the user ever created, **including items in shared orgs**, and leaves org rows behind | Deletion removes personal data and memberships. Shared-org data stays with the org, re-attributed to "Deleted user" | P0 | M | Eng |
| A8 | Viewers can't trigger alerts | 🟡 | `GET /insights` publishes to SNS and writes a row, even as a Viewer (`LowItemInsight.py:259-266`) | Reads have no side effects. Alerts come from a scheduled job | P1 | S | Eng |
| A9 | Errors don't leak internals, and bad input gets a 400 | 🟡 | `str(e)` returned to clients (`BulkImport.py:128,303,324`, `BarcodeLookup.py:177`). Bad numbers return 500, and negative quantities are accepted (`AddItem.py:102`, `UpdateItem.py:120`) | Generic message plus an error code. Validation rejects negative and non-numeric values with 400 | P0 | S | Eng |
| A10 | No wildcard CORS on writes | 🟡 | `*` on DeleteCategory, BulkImport, BarcodeLookup, GetCategories, GetTransactions, LowItemInsight | One shared CORS helper with an allowlist | P1 | S | Eng |
| A11 | Repo holds no personal data | 🟡 | `.playwright-mcp/` (21 files) and `.agent/` (447 files) are tracked despite `.gitignore`, and 11 of them contain email addresses. Stray `lambda/fix_head.py` | Files untracked (and purged from history if the repo ever goes public). Stray script deleted | P1 | S | Eng |
| A12 | Deleted items can't be edited | 🔴 | `UpdateItem.py:94-100` doesn't check `deletedAt` | Updating a deleted item returns 404/410 | P0 | S | Eng |
| A13 | No secrets in the repo | ✅ | No keys, DSNs, or JWT secrets in tracked files | Stays that way (secret scan in CI, item I1) | — | — | — |

## B. Data correctness & org scoping

*Why it matters:* the org is the boundary between stores. A change saved without its org quietly breaks that store's Activity feed and inventory.

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| B1 | Every write records its org and who made it | 🔴 | DeleteItem's activity row has no `orgID`, and it names the item's *creator* instead of the person deleting (`DeleteItem.py:89-100`). Async import writes items and rows without `orgID` (`BulkImportAsync.py:78-103`) | All writes carry `orgID` and the actor. The import job stores `orgID` when the upload link is created | P0 | S | Eng |
| B2 | Every change appears in Activity | 🔴 | RestoreItem and DeleteCategory write no activity row. Delete and category moves don't update `updatedAt` or `version` | Every write records an activity row and bumps `updatedAt` and `version` | P0 | S | Eng |
| B3 | Activity says *what kind* of change | 🟡 | `changeType` is only create/stock_in/stock_out/update/delete. The reason is guessed from quantities (`UpdateItem.py:151-153`) | Add `adjust`, `count`, `restore`, and `import`, plus a structured reason field | P0 | S | Eng |
| B4 | Numbers come back as numbers | 🟡 | Quantity comes back as `10.0` and version as `3.0` (`GetAllItems.py:64`). Imported prices are stored as strings (`BulkImport.py:199`) | Integers stay integers. Prices are stored as numbers | P0 | S | Eng |
| B5 | Orgs are live | 🔴 | Org Lambdas, tables, and `orgID-index` aren't deployed (`docs/aws-live-inventory.md`) | Deployed by the SAM stack and backfilled during migration (launch PRD R7) | P0 | M | Eng |
| B6 | Org management is reachable | 🔴 | There's no create-org route. Rename, transfer, role change, and remove can't be reached from browsers because CORS doesn't allow PATCH (`_logging.py:95`, `Proxy.py:26`) | A create-org route exists. Every org route is callable from the web and the app | P0 | S | Eng |
| B7 | Undocumented tables are documented | 🟡 | `ImportJobs` and `BarcodeCache` are missing from AGENTS.md §3 | Added to AGENTS.md and defined in SAM | P1 | S | Eng |

## C. API contract for a phone client

*Why it matters:* old app versions stay on phones for months. The API must be predictable, versioned, and efficient on slow connections.

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| C1 | One error format with codes | 🔴 | Python returns `{error}`, Auth returns `{message}`, and 409 means five different things | Every error is `{error: {code, message}}` with a documented code list (for example `ITEM_VERSION_CONFLICT`, `PLAN_LIMIT_ITEMS`) | P0 | M | Eng |
| C2 | One date format | 🟡 | ISO strings mostly, but epoch numbers for login and invite expiry | ISO 8601 UTC everywhere | P0 | S | Eng |
| C3 | Stock changes are ± or counts, not totals | 🔴 | Stock in/out sends an absolute quantity with If-Match (`use-stock-actions.ts:71`, `UpdateItem.py:118`) | An `adjust` endpoint (atomic ±N) and a `count` endpoint (exact number plus last-seen version, with a conflict if the item changed) (launch PRD R10.4) | P0 | M | Eng |
| C4 | Item versions reach the client | 🔴 | Proxy drops the ETag (`Proxy.py:224,230`). No `Expose-Headers`. A 412 doesn't include the current item | Version in the response body *and* ETag exposed. A 412 includes the current item | P0 | S | Eng |
| C5 | Incremental sync | 🔴 | `/items` returns the whole inventory every time. Activity scans the whole table and keeps 200 rows (`GetTransactions.py:77-99`) | `GET /items?since=<cursor>` returns only changes and deletions. Activity is paginated by org and indexed by item | P0 | M | Eng |
| C6 | Client version gate | 🔴 | No version header | The app sends `X-Client-Version`. The server returns 426 below the minimum version | P0 | S | Eng |
| C7 | One request ID, end to end | 🔴 | Proxy doesn't forward one. Each hop logs its own ID | One request ID from Proxy, returned in a header, present in every log line and Sentry event | P0 | S | Eng |
| C8 | API reference | 🟡 | The endpoint list exists only in this audit | `docs/api.md` with routes, roles, shapes, and error codes | P1 | S | Eng |

## D. Accounts & sign-in

*Why it matters:* sign-in is the first screen every user and every App Review tester sees.

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| D1 | Login screen is reachable inside the app | 🔴 **Blocker** | `isLocalPreview()` checks `hostname === 'localhost'` (`api.ts:74`). Capacitor runs at `capacitor://localhost` / `https://localhost`, so the app **signs in as a fake preview user**, and 401 handling breaks | Preview mode is gated on `import.meta.env.DEV` only | P0 | S | Eng |
| D2 | Session survives an app restart | 🔴 | Token, org, and role live in `sessionStorage` (`session.ts:15-83`) | Tokens in Keychain/Keystore secure storage, settings in Capacitor Preferences, behind one storage layer so the web keeps working | P0 | S | Eng |
| D3 | Expired session goes to login | 🔴 | `window.location.href = 'login.html?expired=1'` (`api.ts:85`), a file that doesn't exist in the app | Router navigation to `/login?expired=1` | P0 | S | Eng |
| D4 | Cognito sign-in: email and Google (Apple in Phase 6) | 🔴 | Hand-rolled JWT today | Launch PRD R1: Essentials tier, system-browser PKCE (Android Custom Tabs), users migrated with their passwords, account linking by email | P0 | L | Eng |
| D5 | Email verification | 🔴 | None | Required before inviting or upgrading (Cognito) | P0 | S | Eng |
| D6 | In-app account deletion + web page | 🔴 | No endpoint or UI. Depends on A7 | Launch PRD R10.2, plus a web page at `panindo.app/delete-account` | P0 | M | Eng |
| D7 | Invites are accepted by token | 🟡 | The accept flow exists. Email-match behavior isn't verified | Accepting by token works for Apple "Hide My Email" users *(iOS, Phase 6)* | P2 | S | Eng |

## E. Screens on a phone

*Why it matters:* the wrapped app *is* these screens. These problems were found at 360–375px wide.

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| E1 | Respects the notch and home bar | 🔴 | `index.html:5` lacks `viewport-fit=cover`, so the existing `env(safe-area-*)` padding does nothing. The header (`AppLayout.tsx:209`) and bottom sheet (`ItemSheetHost.tsx:55`) have no insets | `viewport-fit=cover`, a top inset on the header, and a bottom inset on sheets and dialogs. Checked on Android 16 edge-to-edge (Capacitor SystemBars insets) and a phone with a display cutout | P0 | S | Eng |
| E2 | No sideways scrolling | 🔴 | **Today** overflows by 8px at 375 and 23px at 360. Restock rows widen the grid (`TodayScreen.tsx:101`), cutting off "Most urgent first" and the Adjust buttons | No screen scrolls sideways at 320–430px (automated check) | P0 | S | Eng |
| E3 | Tap targets ≥44px | 🔴 | Icon buttons are 32px, row checkboxes 16px, filter chips 32px, login tabs 29px, "See all" 38×15 | Every control is ≥44×44, by size or by an enlarged hit area | P1 | M | Eng |
| E4 | Number pad can submit | 🟡 | The iOS numeric keypad has no Return key (`AdjustControls.tsx:77`). Android's keypad has Done, so this is mainly *(iOS, Phase 6)* | A visible confirm button is always present, and the keyboard never covers the focused field (Capacitor Keyboard config) | P1 | S | Eng |
| E5 | Export, print, and template download work | 🔴 | CSV export via a Blob link (`export.ts:20-24`) is ignored by web views. `window.print()` (`StockScreen.tsx:147`) does nothing. The template link (`ImportDialog.tsx:167`) would trap the user on raw CSV | In the app: Filesystem + Share sheet for the CSV and the template. Print becomes "Share PDF" or stays web-only. The web keeps today's behavior | P1 | M | Eng |
| E6 | Honest offline and error states | 🔴 | Offline shows a raw "Load failed". Today also shows **$0 KPIs and "Nothing to restock"** under the error. Team wrongly says team features are unavailable, because `AppLayout.tsx:112` treats any failure as legacy mode | "You're offline" message. Data and empty states are hidden on error. Only a 403/404 means legacy mode | P0 | M | Eng |
| E7 | Status bar follows the theme | 🟡 | No `theme-color` or `color-scheme`, so native controls stay light in dark mode | `color-scheme` set, and the status bar style synced with the theme | P1 | S | Eng |
| E8 | Text is readable and scales | 🟡 | Tab labels are 11px and badges 10px (`AppLayout.tsx:381,398`). The system text size is ignored | Nothing smaller than 12px. Root text size follows the system setting | P1 | S | Eng |
| E9 | Branding says Panindo | 🔴 | "InventoryIQ" in Brand, `<title>`, login, and the export filename (`export.ts:23`) | Panindo everywhere the user can see | P0 | S | Eng |
| E10 | Prices and times are local | 🔴 | USD is hard-coded (`format.ts:1,8`). No timezone handling | Per-org currency (₱/$) and timezone (launch PRD R10.8) | P0 | M | Eng |
| E11 | Last row isn't hidden under the tab bar | 🟡 | On Stock, the tab bar covers the last row while scrolling | Bottom padding equals the tab bar height plus the safe area | P1 | S | Eng |
| E12 | Fonts trimmed | 🟡 | 16 font files (472 KB) ship, including Cyrillic, Greek, and symbol subsets | Latin only, for a smaller app package | P2 | S | Eng |
| E13 | App size | ✅ | 248 KB gzipped JS in total (146 KB entry). Screens load lazily. CSS 16 KB | Stays under 300 KB | — | — | — |
| E14 | No hover-only controls | ✅ | Nothing depends on hover or `title=` | — | — | — | — |
| E15 | Input types | ✅ | Correct `type`/`inputMode`/`autoComplete`. 16px inputs, so iOS doesn't zoom in | — | — | — | — |
| E16 | Error + Try again on every screen | ✅ | Every screen shows an error with a retry button | Wording fixed by E6 | — | — | — |
| E17 | Light and dark themes | ✅ | Light, dark, and system all work | — | — | — | — |
| E18 | Android back button behaves | 🔴 | Not handled. Sheets are URL-based (`?item=`, `?new=1`), so back closes them, but dialogs, menus, and the root screen are unhandled | Back closes the top dialog, sheet, or menu first. Inside the app it goes back a screen. On the home tab it minimizes the app, never returning to login. Predictive back gesture tested | P0 | S | Eng |
| E19 | Works on low-end Android | 🔴 | Never tested on a low-end device | Usable on a 2–3 GB RAM phone with an older Android System WebView: scan-to-adjust in under 10 s, no jank on Stock with 500 items | P1 | S | Eng |

## F. Native capabilities prep

*Why it matters:* these features make Panindo an app rather than a website in a box (Apple Guideline 4.2), and none of them work in today's code.

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| F1 | Scanner works offline and in the app | 🔴 | Quagga is loaded from jsDelivr (`barcode-scan-dialog.tsx:33`) | One `scanBarcode()` interface: native ML Kit in the app, a locally bundled scanner on the web. Camera permission text | P0 | M | Eng |
| F2 | Backend accepts requests from the app | 🔴 | The CORS allowlist lacks `capacitor://localhost` and `https://localhost` (`Proxy.py:12`, `_logging.py:82`, `Authentication.mjs:68`) | Both origins allowed, via one shared helper | P0 | S | Eng |
| F3 | Email links open the app | 🔴 | Reset and invite links are hard-coded to the Netlify site (`Authentication.mjs:58,447`, `OrgInvites.py:217`) | Links use `app.panindo.app`, which serves `/.well-known/assetlinks.json` with the Play App Signing SHA-256 (Apple's file comes in Phase 6). The app routes `/accept` and `/reset-password` | P1 | M | Eng |
| F4 | Push backend | 🔴 | No device-token table or endpoints | Token register/unregister, SNS platform apps, and per-user email alerts via SES (launch PRD R10.6) | P1 | L | Eng |
| F5 | Offline queue + sync engine | 🔴 | No offline code | SQLite queue, tagged by org, 7-day maximum age, syncs when the app opens or resumes (launch PRD R3) | P1 | L | Eng |
| F6 | Content security policy inside the app | 🔴 | The Netlify CSP doesn't apply inside the app bundle, and on the web it blocks Cognito (`netlify.toml`) | A `<meta>` CSP in the app. Netlify CSP updated to allow Cognito | P0 | S | Eng |
| F7 | Router works in the app | 🟡 | BrowserRouter works under Capacitor. `legacyHtml.ts` and Netlify rewrites don't apply there | Deep-link listener plus router routes. Legacy `.html` handling stays web-only | P1 | S | Eng |
| F8 | Android build floor | 🔴 | No Android project yet | Capacitor 8.5, target and compile SDK 36, minSdk 24, Play Billing Library 8, 16 KB page-aligned native libraries (`zipalign -c -P 16`), and a runtime notification-permission prompt (Android 13+) | P1 | M | Eng |

## G. Plans & billing prep

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| G1 | Each org has a plan record | 🔴 | No plan fields. The seat cap is an environment variable (`_org.py:16`) | Org entitlement record: plan, source, buyer, expiry, state | P0 | M | Eng |
| G2 | Limits enforced on the server | 🔴 | No item cap. The seat cap is checked only when sending an invite | Item and seat limits checked on every write. Over the limit means read-only for new items and seats | P0 | M | Eng |
| G3 | Client reads limits from the server | 🟡 | The seat cap of 5 is hard-coded in `TeamScreen.tsx:27` | Limits come from the entitlement response | P0 | S | Eng |
| G4 | Store purchase backend | 🔴 | Doesn't exist | Launch PRD R10.3 (Phase 2) | P1 | L | Eng |
| G5 | One subscription per org | 🔴 | Doesn't exist | Paywall shows "already subscribed via …" | P1 | S | Eng |

## H. Infrastructure & environments

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| H1 | Infrastructure as code | 🔴 | Resources were made by hand | An AWS SAM template deploys the full stack (launch PRD R6) | P0 | L | Eng |
| H2 | Staging environment | 🔴 | Only production exists, and E2E tests run against it | `panindo-staging` with fake data, and E2E runs there | P0 | M | Eng |
| H3 | Import bucket | 🔴 | `inventoryiq-imports` doesn't exist. Uploads have no size limit (`BulkImport.py:100-107`) | Bucket defined in SAM, presigned POST with a size limit, import Lambdas deployed | P0 | S | Eng |
| H4 | Barcode lookup handles public traffic | 🟡 | Uses the UPCItemDB trial tier. Unknown barcodes aren't cached (`BarcodeLookup.py:160`) | Misses cached for 7 days, a per-org daily quota, and the org's own items checked first | P1 | S | Eng |
| H5 | Logs are actually recorded | 🔴 | Python logs are off unless `LOG_STDOUT=1` (`_logging.py:27`), so CloudWatch is mostly empty | Logs on, structured, kept **30 days** (as the privacy policy promises) | P0 | S | Eng |
| H6 | Backups match the privacy policy | 🔴 | DynamoDB point-in-time recovery status is unknown | Point-in-time recovery on (35 days), as the privacy policy states | P0 | S | Eng |
| H7 | Cost guardrail | 🔴 | No budget alarm | AWS Budget alarm at $10/month | P0 | S | **You** (one click), or Eng in SAM |
| H8 | Error-tracking cost | 🟡 | Sentry `traces_sample_rate` = 1.0 (`_logging.py:18`) | 0.1 or lower, to stay within Sentry's free tier | P1 | S | Eng |
| H9 | Region and account | ✅ | us-east-1, existing account | Decided | — | — | — |

## I. Quality, testing & observability

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| I1 | CI works | 🔴 | `ci.yml` uses `secrets.*` in a step `if` (lines 20 and 27), which makes the file invalid. The last 2 runs failed. It never runs typecheck, build, unit tests, or pytest | CI runs typecheck, build, `test:unit`, pytest, and a secret scan on every PR. E2E runs against staging | P0 | S | Eng |
| I2 | Risky backend paths are tested | 🔴 | 19 of 21 Lambdas have no tests | Tests for Proxy auth, adjust/count, idempotency, org roles and limits, deletion, and migration, all running offline with moto | P0 | L | Eng |
| I3 | Existing tests pass | 🔴 | 2 tests in `test_GetAllItems.py` fail because they still pass `userID` as a query parameter | Fixed and running in CI | P0 | S | Eng |
| I4 | E2E covers write flows | 🟡 | 5 specs, all read-only, run against production | Add, adjust, count, delete/restore, invite, and import flows on staging | P1 | M | Eng |
| I5 | Errors reach Sentry | 🟡 | Proxy and 9 Lambdas swallow or print errors. Auth's catch-all returns 500 without reporting it (`Authentication.mjs:514-529`) | Every handler reports errors tagged with user, org, and request ID | P0 | S | Eng |
| I6 | Frontend monitoring | 🔴 | No Sentry or analytics in the frontend | `@sentry/capacitor` (and the web SDK) plus PostHog events for the launch metrics | P1 | S | Eng |
| I7 | Unit tests for app logic | ✅ | 25/25 TS unit tests pass | Keep them, and add tests for `api.ts` | — | — | — |
| I8 | Role checks on writes | ✅ | Every item, category, and import write requires Editor or above | — | — | — | — |
| I9 | Structured logging helper | 🟡 | `log_json` exists, but the cron Lambdas use `print` and Auth uses `console.log` | One logger everywhere | P1 | S | Eng |
| I10 | Local development works | ✅ | `npm run dev` with local preview mode | D1 limits preview mode to dev builds | — | — | — |

## J. Brand, legal & store assets

| ID | Check | Status | Evidence | Ready means | Pri | Size | Owner |
|---|---|---|---|---|---|---|---|
| J1 | Marketing site with Privacy, Terms, Delete-account, and Support pages | 🟡 Built, not deployed | `site/` holds 6 static pages with no JS, no cookies, and no trackers. It was checked at 320–1440px in light and dark with no overflow. See `site/README.md` for deploy steps and the placeholder list | Deployed to `panindo.app`, with security headers verified after deploy | P1 | S | **You** (Netlify) |
| J2 | Legal text reviewed | 🟡 | Drafts with placeholders: [OPERATOR LEGAL NAME], [MAILING ADDRESS], [EFFECTIVE DATE], [CITY] | Placeholders filled. Lawyer review when affordable | P1 | — | **You** |
| J3 | Policy promises match the system | 🟡 | The policy will promise 30-day log retention, 35-day backups, 30-day account deletion, and 30-day trash | Kept true by H5, H6, D6, and A7 | P0 | — | Eng |
| J4 | Domain + support email | 🔴 Not done | `panindo.app` is available but not registered | Registered, and `support@` forwards via Cloudflare Email Routing | P0 | S | **You** |
| J5 | Store listing assets | 🔴 | None yet | App icon, screenshots (English and Filipino), descriptions, and a demo account | P2 | M | You + Eng |
| J6 | Google Play developer account | 🔴 Not done | Setup steps written in this session | Play Console (individual, $25) verified, app created with package `app.panindo`. Apple waits for Phase 6 | P1 | — | **You** |

---

## The readiness gate (Definition of Ready)

The mobile build (launch PRD Phase 1) starts when **all 51 P0 items** are done:

| Area | P0 items |
|---|---|
| A | A1–A7, A9, A12 |
| B | B1–B6 |
| C | C1–C7 |
| D | D1–D6 |
| E | E1, E2, E6, E9, E10, E18 |
| F | F1, F2, F6 |
| G | G1–G3 |
| H | H1–H3, H5–H7 |
| I | I1–I3, I5 |
| J | J3, J4 |

These three checks must also pass:
1. Staging passes the full E2E suite.
2. A screenshot test at 320, 375, and 430px shows no sideways scrolling on any screen.
3. The migration rehearsal has passed twice (launch PRD R7).

## Suggested order

| Sprint | Goal | Items |
|---|---|---|
| **R0: quick wins (≈1 week)** | Stop the leaks and unblock the app shell. All small | A1 deploy, A3, A6, A9, A12, B1, B2, B4, C2, C4, C7, D1, D3, E1, E2, E9, E18, F2, H5, I1, I3, I5 |
| **R1: foundations (≈3–4 weeks)** | The Phase 0 backend | H1–H3, H6, H7, B3, B5, B6, A2, A4, A5/D4/D5 (Cognito), A7/D6 (deletion), C1, C3, C5, C6, G1–G3, E6, E10, D2, F1, F6, I2, J3 |
| **R2: pre-beta polish** | Support work for Phase 1 | E3, E4, E5, E7, E8, E11, E19, F8, F3, F4, F5, F7, D7, A8, A10, A11, B7, C8, H4, H8, I4, I6, I9, G4, G5 |

## What you do (non-code)

1. **Deploy the alert hotfix (A1).** The command is in the launch PRD's Engineering Notes, and in the session.
2. **Register `panindo.app`** and set up `support@panindo.app` forwarding (J4).
3. **Create a $10 AWS budget alarm (H7):** Billing console → Budgets → Create. It takes about 2 minutes.
4. **Deploy `site/`** as a second Netlify site at `panindo.app` (J1), and fill in the legal placeholders (J2).
5. **Enroll in Google Play Console (J6).** Individual account, $25. Create the app "Panindo" with package `app.panindo`. Apple waits for Phase 6.
6. **Recruit 12–20 beta stores** (US and PH) for Google's 14-day closed test.

## Out of scope for readiness

These belong to Phases 1–2 of the launch PRD, not to readiness:
- the mobile build itself (Capacitor project, native plugin wiring, store submission)
- store billing integration (G4)
- push delivery (F4)

Readiness prepares the app and backend so that those phases are mostly wiring.
