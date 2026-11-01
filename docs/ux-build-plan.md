# Panindo UI/UX build plan

Version 4 · 2026-10-31 · status: **for your read-through, nothing built yet** · v3 added §9 Edge cases; v4 folds them into each phase as build steps, adds §10 already-handled behaviour, and updates verification and risks

One document for the whole job: what we audited, what we decided, how each change is built, and how we check it. It folds in your three findings, the 20-detail audit, the grill decisions and both plan reviews (code + UI/UX).

---

## 1. Ground rules

- Work happens in the current checkout (`feat/item-expiry-alerts`, which already has uncommitted report changes). **No commits, no pushes, no new packages, no backend deploy.** You commit.
- Follow AGENTS.md: shadcn preset tokens only, sonner toasts, `ConfirmDialog` for anything not undoable, errors rendered in the page, no new design system.
- Every phase ends green: `npm run build`, `npm run test:unit`, slopcheck (`bun ~/development/slopcheck/cli.ts audit . --no-clones`).
- **View-only users** (role `viewer`, `shell.canEdit === false`): every new control in this plan is hidden or disabled for them, the same way current edit controls are. Called out per phase.
- Two review stops: after Phase 4, and after Phase 7.
- **Cross-phase guards** (apply in every phase that touches the area):
  - **Org switch:** anything in flight for the old org (pending saves, preview, Insights load, Undo toasts) is flushed or dropped; late responses are ignored when `getCurrentOrg()` no longer matches.
  - **Lost edit access (403 on a save):** roll back, toast "You no longer have edit access", reload the shell's role.
  - **Session expiry (401):** `check401()` as today; the P5 `beforeunload` prompt protects unsaved taps.
  - **Offline:** every failure path names what happened and offers Retry where a read failed; nothing fails silently.

## 2. Audit summary (the 20 details)

| # | Detail | Status today | Plan |
|---|---|---|---|
| 1 | Skeleton loaders | ✅ mostly (`AppLayout.tsx:248`, `StockStates.tsx:6`, `KpiStrip.tsx:38`) | P1: Activity count "Loading…" → skeleton |
| 2 | Optimistic updates | ❌ save waits for the server (`use-stock-actions.ts:89`) | **P5** |
| 3 | Command menu | ❌ | **Skipped** (your call; mostly phone users) |
| 4 | Shortcut hints | ❌ | **Skipped** (goes with #3) |
| 5 | Undo toasts | ⚠️ Undo exists, but a confirm dialog shows first | **P4** |
| 6 | Stale-while-revalidate | ⚠️ items yes; Insights wipes and refetches | Solved by **P7** (Insights reads the shared cache) |
| 7 | Pre-rendering | ❌ route chunks load on first visit | **P3** |
| 8 | BlurHash | N/A, the app has no images | — |
| 9 | View transitions | ❌ hard cuts between pages | **P3** |
| 10 | Swipe-to-dismiss sheets | ❌ mobile item sheet has no swipe | **P6** |
| 11 | Interruptible animations | ✅ CSS transitions on sheet/dialog | keep |
| 12 | Predictive back | N/A, browser/OS handles it on web | — |
| 13 | Hit slop | ✅ `touch:min-h-11` variant (`index.css:9`) | spot-check in P1 |
| 14 | Safe area insets | ✅ `viewport-fit=cover`, `env(safe-area-*)` everywhere | keep |
| 15 | One-time code autofill | N/A, no codes (password + email link) | revisit with Cognito |
| 16 | Tabular numbers | ⚠️ partial | **P1** |
| 17 | Balanced headlines | ✅ page headers | P1: dialog/sheet titles |
| 18 | Continuous corners | ❌ | **P1** |
| 19 | Idempotency keys | ✅ add/import send keys; delete/restore guarded by DynamoDB conditions (410/409); quantity by `If-Match` | nothing to build |
| 20 | Safe triangle | N/A, no hover submenus | — |

## 3. Your three findings

1. **Print shows no preview.** Print goes straight to `window.print()`. → **P2** adds an in-app preview.
2. **Insights isn't really insights.** The server version repeats Today's counts, uses fixed sentences, always suggests "2× threshold", ignores expiry and history, and sends an SNS/SQS message on every visit. → **P7** rebuilds it in the browser.
3. **Page switches aren't smooth.** Hard cuts, plus route code loads on first visit. → **P3**.

## 4. Decisions (agreed)

| Topic | Decision |
|---|---|
| Insights home | Keep `/insights`, linked from Today |
| Insights data | Computed in the browser from items + `GET /transactions?since=<30 days ago>` (uncapped). Stop calling `GET /insights` |
| Alerts | Low-stock alerts come only from DailyAlert's daily run (no more alert-on-visit) |
| Runs out soon | Estimate only with 2+ sales/use changes across 3+ days; list items running out within 14 days, soonest first, top 8 + See all |
| Expiring soon | `EXPIRY_WINDOW_DAYS = 7` (`lib/dashboardStats.ts:51`, same as DailyAlert) |
| Not moving | In stock, no stock in/out for 30 days; items younger than 30 days are skipped |
| Fast taps | **Merge into one save** (like the Stock row stepper): number changes on every tap, one save ~1 s after the last tap, one toast with Undo |
| Delete | Undo only for single delete and bulk delete of fewer than 10 items. **Confirm stays** for 10+ items or Select all, Stop counting, Delete category |
| Print preview | Large dialog; full screen on phones |
| Page transition | ~150 ms cross-fade of the page content; nav stays put; off under reduced motion |
| Swipe sheet fallback | If Base UI Drawer fights the scrolling sheet: keep `Sheet`, add a drag handle that closes on swipe down |
| Review stops | After P4, after P7 |

## 5. Phases

### P1 · CSS polish (#1, #16, #17, #18) · small

- **Tabular numbers:** `tabular-nums` on Stock table quantity/price/value cells, Today stats, Insights numbers; print CSS `#print-table td.num { font-variant-numeric: tabular-nums }`.
- **Balanced titles:** `text-balance` on `DialogTitle` and `SheetTitle`.
- **Squircle corners**, scoped (not every `rounded-` class, which would hit inputs, rings and `rounded-none`):
  ```css
  @supports (corner-shape: squircle) {
    :is([data-slot="card"], [data-slot="dialog-content"], [data-slot="sheet-content"], [data-slot="button"]):not(.rounded-full) {
      corner-shape: squircle;
    }
  }
  ```
  Chromium gets smooth corners; Safari and Firefox look as they do today. No radius token changes. Check `overflow-hidden` cards for clipping.
- **Activity count:** replace "Loading…" (`ActivityScreen.tsx:117`) with a small skeleton, `aria-busy="true"` + sr-only "Loading".
- **Hit slop spot-check:** small icon buttons at 390 px with `touch:` variant.

### P2 · Print preview (finding 1) · small

- Extract the report table into an **id-less `ReportTable`** component. Used twice: inside the existing hidden `#print-section` (page-level, what actually prints) and inside the preview. No duplicate ids; print CSS untouched.
- `ReportDialog` Print → builds the report (unchanged) → opens **`PrintPreviewDialog`** instead of printing.
  - Desktop: wide dialog. Phone: full screen. White "paper" card with a thin border (stays white in dark theme by design). Wide table scrolls inside the paper only.
  - Sticky footer: **Back** (returns to the date picker) and **Print or save PDF**, both 44 px targets.
  - Focus moves into the dialog; Back returns focus to the Print button.
- Preview state is held **separately** from the print `report` state, so `afterprint` (which clears the report, `StockScreen.tsx:78`) doesn't close the preview mid-flow. Clicking Print: set the report, close the preview, `window.print()`.
- Layout unchanged per the Oct 30 learning: Category column per row, category headings, "Description" column.
- **Edge cases built in:**
  - 0 items → Print disabled in the report dialog with "Nothing to print yet"; the preview never opens empty.
  - Selection report → title says "Selected items" (matches the `_selected` CSV name).
  - The preview is a snapshot: "As of <time>" shown; printing prints that snapshot even if stock changes meanwhile.
  - Ctrl/⌘+P with the preview open prints the page-level report, not the dialog.
  - Org switch closes the preview.
  - Check: 500+ rows scroll smoothly at 390 px; iOS Safari prints after the preview closes.

### P3 · Smooth page switches (finding 3, #7, #9) · medium

1. **Measure first** on `npm run dev:local` (agent-browser, throttled): Today → Stock → Activity → Insights. Record what the jank actually is.
2. **Preload (#7):** move each `import()` in `App.tsx` into a named loader used by both `lazy()` and an idle preloader that loads all signed-in screens via `requestIdleCallback` after first paint. One mechanism, no hover handlers.
3. **Cross-fade (#9):** the app uses `BrowserRouter`, where NavLink's `viewTransition` prop does nothing. So nav links get a click handler:
   `document.startViewTransition(() => flushSync(() => navigate(to)))`
   only when the API exists and `prefers-reduced-motion` is not set; otherwise normal navigation. Preload must land first, or the fade would show a skeleton.
   - CSS: ~150 ms fade on `::view-transition-old(root)` / `::view-transition-new(root)`; sidebar and tab bar get their own `view-transition-name` so they don't fade; `@media (prefers-reduced-motion: reduce)` turns the animations off.
   - Check the fixed tab bar, sheets and toasts during a transition.
4. **Focus/announce:** after a route change, focus `#main` and keep `document.title` updated, so screen readers hear the new page.
5. **Edge cases built in:**
   - Idle preload wraps each loader in `.catch(() => {})`; a stale chunk after a deploy is left to the existing error boundary, which already offers Reload (`error-boundary.tsx:8`).
   - Clicking the nav link of the current page: no transition, no navigation.
   - Only nav-link clicks fade. Back/forward, `?item=`, `?status=` and other URL changes keep today's behaviour.
   - Rapid clicks: the newer `startViewTransition` replaces the running one; last click wins, no frozen frame.
   - An open sheet or dialog closes with navigation as today; the fade must not capture it half-closed.

### P4 · Undo-only delete (#5) · small → **review stop**

- **Single delete** (item sheet, `ItemPanel.tsx:110`): no confirm. Delete → item sheet closes → focus back to the list → toast "Deleted Rice" with **Undo** (existing `deleteItems`, `use-stock-actions.ts:172`).
- **Bulk delete** (`StockScreen.tsx:361`): fewer than 10 items → no confirm; **10+ items or Select all → confirm stays**. Toast "Deleted 6 items · Undo", 15 s for 2+ items (10 s for one).
- Remove the now-unused `bulk-delete` dialog state and `busy` plumbing.
- **Toast position:** check on a phone that toasts sit above the bottom tab bar + safe area; set Sonner `offset`/`mobileOffset` if not.
- Viewers: Delete stays hidden (no change).
- **AGENTS.md §4C.4:** amend to "destructive actions that can't be undone use `confirm-dialog`; undoable ones use an Undo toast".
- **New e2e:** Delete → Undo → item is back.
- **Edge cases built in:**
  - The 10+ rule counts selected items whatever filter or search is on; Select all always confirms.
  - Restore returns 409 (someone restored it first) → toast "Already restored", reload, no error toast. Delete returns 410 → "Already deleted".
  - Bulk delete partly fails → existing behaviour: failures counted, Undo restores only what was deleted.
  - Org switch dismisses open Undo toasts, so Undo can't run against the wrong store.
  - An item with a pending quantity save (P5) is flushed or cancelled before it's deleted.
  - Toast offset clears the tab bar, safe area **and** the floating bulk bar when it's visible.

### P5 · Optimistic quantity (#2) · medium

- **One rule for everyone:** `setQuantity` writes the new quantity into the cache **before** the PUT, so every screen (Today, Stock, sheet) updates instantly.
- **Fast taps merge into one save:** the item sheet's Adjust controls and Today's Restock use the same coalescing the Stock row stepper uses (`use-row-stepper.ts`, `stepper.ts` `serialize`): number moves on every tap, one save ~1 s after the last tap, one toast "Rice: 12 → 18 · Undo". Only one save per item is ever in flight, so no self-made 412s and the Undo guard (`use-stock-actions.ts:90`) stays correct.
- `AdjustControls` stops disabling itself while saving (`AdjustControls.tsx:36-45`); a small "Saving…" hint shows on the item while a save is pending.
- **Background reloads don't clobber pending numbers:** the store keeps a set of item IDs with a pending save; `reloadItems` keeps the cached row for those.
- **Failure:** cancel anything pending for that item, reload it from the server, and say what happened: toast "Couldn't save Rice. It's back to 12" (aria-live via sonner). 412 keeps today's "changed by someone else" message.
- **Count review** (`CountReviewDialog.tsx:49`) keeps `silent` mode and still awaits each save, because it counts failures from the result.
- **Receive** (Today) is one submit → optimistic + same failure path.
- Viewers: no adjust controls (no change).
- **Test first:** unit test for the pure "pending quantity / rollback target" helper in `tests/unit/ts/`.
- **Edge cases built in:**
  - **One queue per item, owned by the store** (`inventory-store.tsx`), shared by the row stepper, the item sheet, Today and Receive. Not one coalescer per component, so two places adjusting the same item merge instead of fighting. **test**
  - Clamp at 0 inside the shared queue (as `stepper.ts:8` does today). **test**
  - Undo pressed while new taps are pending: cancel the pending taps, then run the undo save. **test**
  - Pending save + reload arrives: keep the cached row; the next reload after the save settles takes the server row. **test**
  - Tab close / reload with a save pending: `beforeunload` prompt only while something is pending; flush on `pagehide`.
  - Save returns 404/410 (deleted elsewhere): drop the item from the cache, toast "Rice was deleted by someone else".
  - Count mode: the count review compares against the latest cached quantity, so sheet adjustments made mid-count show up in the review. Browser check.

### P6 · Swipe-to-dismiss item sheet (#10) · medium

- **Spike (30 min cap)** against the real item sheet with long `ItemHistory` content at 390 px.
- If it works: on phones `ItemSheetHost.tsx` renders Base UI `Drawer` (`@base-ui/react@1.9.0/drawer`, installed) instead of `Sheet side="bottom"`; desktop keeps the right `Sheet`.
- **Either way:** swipe only from the handle/header; content scrolls on its own (`overscroll-contain`); visible Close button stays; Escape closes; focus trapped while open and returned to the row that opened it; `role="dialog"` with the item name as title. Inputs with the keyboard open must not trigger a dismiss.
- Fallback if the spike fails: keep `Sheet`, add a drag handle that closes on swipe down.
- **Edge cases built in:**
  - Swipe close goes through the same `use-sheet-params` close path as the Close button, so a deep-linked sheet (`?item=<id>`) clears its URL keys (already true for Close, `use-sheet-params.ts:55`).
  - Back button keeps closing the sheet instead of leaving the page.
  - Swipe is disabled while an input inside the sheet has focus (iOS keyboard).
  - Spike tests both a short sheet and a long `ItemHistory`.
  - Item deleted elsewhere while open: the existing "Item not found" state (`ItemSheetHost.tsx:72`) still closes by swipe.

### P7 · Real Insights (finding 2, #6) · large → **review stop**

**Data.** `InsightsScreen` loads `getTransactions(<30 days ago>)` (uncapped, already used by the stock report) plus items from `useInventory()`. No `GET /insights` call; `getInsights` is deleted from `api.ts` (only caller). Lambda and API route stay. The page shows instantly from the item cache while history loads.

**Pure helper `frontend/src/lib/insights.ts`**, reusing `deriveDashStats`, `daysUntilExpiry`, `EXPIRY_WINDOW_DAYS`, `isWasteNote` (`lib/activity.ts:46`):

| Card | Rule | Wording |
|---|---|---|
| Health | Same formula as DailyAlert (−25 per out, −10 per low) so it matches the daily summary | gauge + "N of M items need attention" |
| **Running out** | daily use = sales/use over the last 30 days ÷ days covered. "Use" = `stock_out` that isn't waste/damage, minus Undo entries. Needs 2+ such changes across 3+ days. Show items with ≤14 days left, soonest first, top 8 + See all | "About 3 days left" (whole days; under 1 → "Runs out today") |
| **Expiring soon** | `expiresAt` within 7 days (and expired), with value at cost (`priceOf × quantity`) | "Expires in 4 days · ₱1,200 of stock" |
| **Not moving** | quantity > 0, no stock in/out in 30 days, item older than 30 days | "No sales in 30+ days" |
| **Waste & damage** | totals (units + value) of Waste/Damaged notes in 30 days | "From items you marked as waste or damaged" |
| Category risk | low + out per category, from the cache | as today |

**States, per card:** skeleton while loading; empty state that says what to do ("Add items to see this", "Nothing expiring this week"); not-enough-data copy that says when it will appear ("We need a few sales over 3 days to estimate this"); error with **Retry** if history fails to load (cache-based cards still show).

**Links:** card rows are real links to the item sheet (`?item=<id>`) or to existing Stock filters (`?status=out|low`). No new Stock filters in this job; "See all" opens a dialog listing the full card.

**Footer note:** "Low-stock alerts are sent once a day."

**Tests:** `tests/unit/ts/insights.test.ts` with fixed dates for every threshold: 14-day cutoff, 30-day "not moving", 2 changes / 3 days, waste excluded from use, Undo netted, expired vs. expiring. Seed: extend `scripts/local_seed.py` with backdated sales so "running out" and "not moving" show in the browser.

**Edge cases built in** (all **test** in `insights.test.ts` unless noted):
- Empty store: empty state per card; the gauge says "Add items to see your stock health" instead of a misleading 100.
- Price missing, 0 or a string → `priceOf()`; value text hidden when it would read "₱0".
- `expiresAt` empty or invalid → ignored; past → "Expired N days ago", listed first under Expiring.
- Quantity 0 → only in Out of stock, never in Running out or Not moving.
- Item younger than 30 days → skipped by Not moving; Running out counts from its first change and still needs 3+ days.
- History rows for deleted items or without `itemID` → ignored. Matching is by `itemID` only, never by name.
- Undo nets against the change it reverses; Count fix and Waste/Damaged excluded from "use"; waste counted only in Waste & damage.
- Days counted in device local time (`createdAt` is UTC); test a change at 23:30 local.
- Very large 30-day history: `GET /transactions?since=` returns everything since the date (`GetTransactions.py:95-111`); a response over Lambda's 6 MB limit fails → error state with Retry. Server-side paging is out of scope; ceiling noted in the trail learning. (browser)
- Stale data: Refresh reloads items + history; "Updated <time>" under the header. (browser)
- Org switch while history loads → response dropped. (browser)
- Viewer: cards and links work; the item sheet opens read-only. (browser)

**Docs:** AGENTS.md line on `InsightsScreen` ("the only caller of `GET /insights`") → "computes insights from the item cache and `GET /transactions?since=`". Save a trail learning once built.

## 6. Verification (per stop)

| Check | How |
|---|---|
| Build, types, unit | `npm run build`, `npm run test:unit` |
| Erosion | slopcheck audit, no new hot spots |
| E2E | `tests/e2e/today.spec.ts`, `navigation.spec.ts`, new Delete → Undo spec |
| Unit tests added | `insights.test.ts` (all P7 edge cases), pending-queue helper (merge across callers, clamp at 0, Undo with pending taps, reload during save) |
| Browser (`npm run dev:local`, agent-browser, 390 px and desktop, light + dark) | print preview + print, empty report, 500-row preview; page switch before/after, same-page click, rapid clicks, back/forward; delete + Undo + toast above tab bar and bulk bar, 10+ confirm; optimistic tap with API forced to fail, tab-close prompt, same item from row + sheet; swipe sheet with long history, deep link, keyboard open; Insights numbers against seeded data, empty store, Refresh; viewer login sees no edit controls; org switch mid-save and mid-load |
| Reviews | factory-code on the full diff, factory-uiux browser pass |
| Then | stop. You commit |

## 7. Risks

| Risk | Mitigation |
|---|---|
| View transition + lazy chunk = double fade | Preload lands first; measure before/after |
| Base UI Drawer is new | 30-min spike, handle-only fallback |
| Optimistic number overwritten by a background reload | pending-ID set in the store |
| Undo-only bulk delete mistakes | Confirm kept for 10+ / Select all; 30-day restore in Deleted items |
| Insights numbers disagree with the daily alert | Same health formula and expiry window as DailyAlert |
| Squircle clipping | Scoped selector; Chromium-only enhancement |
| Two components adjusting the same item fight each other | One per-item queue in the store, shared by all callers |
| Unsaved taps lost on tab close or session expiry | `beforeunload` prompt while pending; flush on `pagehide` |
| Undo or a pending save lands in the wrong store after an org switch | Flush/drop on switch; dismiss Undo toasts; org guard on late responses |
| Busy store's 30-day history exceeds Lambda's 6 MB response | Error state with Retry; server-side paging is a later job |

## 8. Order and size

P1 (S) → P2 (S) → P3 (M) → P4 (S) → **stop** → P5 (M) → P6 (M, spike) → P7 (L) → **stop**.

## 9. Edge cases to resolve

Full list for reference. Every row is now built into its phase in §5 ("Edge cases built in"). Rows marked **test** get a unit or e2e test; the rest are checked in the browser pass.

### Across all phases

| Case | Resolution |
|---|---|
| Org switch while something is pending (a save, a preview, Insights loading) | Pending quantity saves for the old org are flushed before the switch or dropped with a toast; preview dialog closes; Insights ignores responses whose org no longer matches (same `getCurrentOrg()` check the store already uses). |
| Session expires (401) mid-action | `check401()` sends to login as today; unsaved taps are lost, so P5's `beforeunload` warning (below) also covers this path. |
| Role downgraded to viewer while the page is open (save returns 403) | Treat like a failed save: roll back, toast "You no longer have edit access", reload the shell's role. |
| Offline / flaky network | Failed save → rollback toast names the restored number; Insights history error shows Retry; preload failures are swallowed (the route loads normally on click). |

### P2 · Print preview

| Case | Resolution |
|---|---|
| Report with 0 items (empty store or empty selection) | Print button disabled in the report dialog with "Nothing to print yet"; preview never opens empty. |
| Large store (500+ rows) | Preview renders the same table; check scroll performance at 390 px. No virtualisation unless it measurably lags. |
| Items change after the preview opens | The preview is a snapshot with its "As of" time shown; printing prints that snapshot, not live data. |
| Selection report | Title says "Selected items" like the CSV name does, so a partial sheet isn't mistaken for a full count. |
| iOS Safari print from inside a dialog | Print closes the preview first, then `window.print()` on the page-level section (already the plan); verify on iOS. |
| User presses Ctrl/⌘+P with the preview open | Prints the page-level report (same snapshot), not the dialog chrome. |

### P3 · Page switches

| Case | Resolution |
|---|---|
| New deploy while the app is open → old chunk 404s | Idle preload catches and ignores errors; on a failed lazy load the existing error boundary offers Reload. **test**: none, browser check by deleting a chunk. |
| Clicking the nav link for the page you're already on | No transition, no navigation. |
| Back/forward buttons, `?item=` / `?status=` URL changes | No fade: only nav-link clicks fade. Sheets and filters keep their own animations. |
| Rapid clicks (Today → Stock → Activity in < 150 ms) | `startViewTransition` skips the previous transition; last click wins. Check no frozen frame. |
| Item sheet or dialog open while navigating | The sheet closes with navigation as today; the fade doesn't capture a half-closed sheet. |

### P4 · Undo-only delete

| Case | Resolution |
|---|---|
| Undo pressed after navigating away or switching org | Undo restores by itemID against the org it was deleted in; if the org changed, the toast is dismissed on switch. |
| Someone else restores or deletes the same item first | Restore returns 409 / delete 410: toast "Already restored" / "Already deleted", reload, no error noise. |
| Bulk delete partly fails | Existing behaviour: toast counts the failures; Undo restores only the ones that were deleted. |
| Count of 10+ with a filter or search on | The 10+ rule counts the selected items, whatever filter is on. "Select all" always confirms. |
| Deleting an item that has a pending quantity save (P5) | Flush or cancel the pending save first, then delete, so the save doesn't 410 after the delete. |
| Toast lost behind the bottom tab bar or the floating bulk bar | Sonner `mobileOffset` above tab bar + safe area + FloatingBar height when it's visible. Browser check at 390 px. |

### P5 · Optimistic quantity

| Case | Resolution |
|---|---|
| Same item adjusted from two places (row stepper and item sheet, or Today and the sheet) | One per-item pending queue in the store, shared by every caller, not one coalescer per component. **test** |
| Taps below zero | Clamp at 0 (as `stepper.ts:8` already does) in the shared queue. **test** |
| Closing the tab / reloading with a save pending | `beforeunload` prompt only while a save is pending; flush immediately on `pagehide`. |
| Undo pressed while new taps for that item are pending | Undo applies to the confirmed save it belongs to; pending taps are cancelled first, then the undo save runs. **test** |
| Item deleted by someone else while a save is pending (404/410) | Remove it from the cache, toast "Rice was deleted by someone else". |
| Count mode active and the same item is adjusted from the sheet | Count review compares against the latest cached quantity; changes made after the count started show in the review. Browser check. |
| A background reload arrives mid-save | Pending item IDs keep their cached row (planned); after the save settles, the next reload takes the server row. **test** |

### P6 · Swipe sheet

| Case | Resolution |
|---|---|
| Opened from a deep link (`?item=<id>`) | Swipe close removes `?item=` exactly like the Close button (same `use-sheet-params` path). |
| Browser/Android back while the sheet is open | Closes the sheet (URL param change), doesn't leave the page. Already true; keep it. |
| Typing with the iOS keyboard open | Swipe disabled while an input is focused. |
| Sheet content shorter than the screen vs. long `ItemHistory` | Both checked in the spike; swipe only from the handle/header. |
| Item deleted while its sheet is open (by someone else) | Sheet shows the existing "item not found" state; swipe still closes. |

### P7 · Insights

| Case | Resolution |
|---|---|
| Brand-new store (no items / no history) | Empty states per card; no gauge of 100 for an empty store, show "Add items to see your stock health". **test** |
| Item price missing, 0 or a string | `priceOf()`; value lines hidden when price is 0 so "₱0 of stock" never shows. **test** |
| `expiresAt` empty, invalid, or already past | Reuse `daysUntilExpiry`: invalid → ignored; past → "Expired N days ago" at the top of Expiring. **test** |
| Item already at 0 | Not in Running out (it's in Out of stock); not in Not moving. **test** |
| Item created less than 30 days ago | Skipped by Not moving; Running out uses days since its first change, still needs 3+ days. **test** |
| Transactions for deleted items or with no `itemID` (legacy rows) | Ignored; match by `itemID` only, never by name (renames would break name matching). **test** |
| Undo, Count fix, Waste/Damaged notes | Undo nets against the change it reverses; Count fix and waste excluded from "use"; waste counted in Waste & damage only. **test** |
| Day boundaries | Days counted in the device's local time (`createdAt` is UTC ISO), same as the stock report. **test** with a timestamp near midnight. |
| Busy store, very large 30-day history | `GET /transactions?since=` scans everything since then (`GetTransactions.py:95-111`); a Lambda response over 6 MB fails. Watch: show the error state with Retry; note the ceiling in the trail learning. Paging the endpoint is out of scope. |
| Stale numbers (another device changed stock) | Refresh button reloads items + history; "Updated <time>" under the header. |
| Org switch while history loads | Response dropped if the org changed (same guard as the store). |
| Viewer | Cards and links work (the item sheet is read-only for viewers); nothing on the page edits. |

## 10. Already handled today (checked in the code, keep as is)

| Behaviour | Where |
|---|---|
| Stale chunk after a deploy shows "This page failed to load" with a Reload button | `frontend/src/components/error-boundary.tsx:8-26` |
| Item sheet for a missing or deleted item shows "Item not found" | `frontend/src/components/item-sheet/ItemSheetHost.tsx:72` |
| Closing a deep-linked sheet replaces the URL without the sheet keys | `frontend/src/app/use-sheet-params.ts:25, 55` |
| Row stepper clamps at 0 | `frontend/src/screens/stock/stepper.ts:8` |
| Background item reload keeps rows mounted (skeleton only on an empty cache) | `frontend/src/app/inventory-store.tsx:85` |
| Delete and restore can't run twice (DynamoDB conditions → 410 / 409) | `lambda/DeleteItem.py`, `lambda/RestoreItem.py:128` |
| `GET /transactions?since=` returns the full range, paginated server-side | `lambda/GetTransactions.py:61, 95-111` |
| Bulk delete counts failures and Undo restores only what was deleted | `frontend/src/app/use-stock-actions.ts:173-205` |
