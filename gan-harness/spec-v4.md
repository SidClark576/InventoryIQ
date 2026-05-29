# InventoryIQ Frontend Improvement Spec — v4

> GAN Harness Planner output. Generator implements; Evaluator scores against the rubric in section 6.
> Target: ambitious-but-achievable in a single ~2-hour generation pass.

---

## 0. Mission

Transform InventoryIQ from a generic "Tailwind template" SaaS dashboard into a **dark-luxury operations terminal** — the visual feel of Bloomberg Terminal crossed with the Linear app. The app must feel deliberate, dense-but-breathable, and premium. Every surface should look like a real product screenshot, not a scaffold.

This is a **frontend-only** pass. The AWS Lambda/DynamoDB backend is deployed and frozen. Do not change API request/response shapes, endpoint paths, or auth logic. Only `frontend/*.html`, `frontend/style.css`, and the presentation layer of `frontend/*.js` may change.

---

## 1. Visual Direction & Design System

### 1.1 Mode decision
**Dark mode is the primary and only mode for this pass.** No light/dark toggle. The Material color token system currently embedded in each page's `tailwind.config` is a light palette and is effectively unused decoration — we are replacing the *applied* colors with a dark luxury palette using arbitrary values and a small set of new tokens. Do not attempt to wire Tailwind `darkMode: "class"` theming; instead apply the dark palette directly.

### 1.2 Palette (exact)

| Role | Hex | Usage |
|------|-----|-------|
| `--bg-base` | `#0a0e1a` | App background (deepest navy-black) |
| `--bg-surface` | `#11182b` | Sidebar, header, primary panels |
| `--bg-surface-2` | `#161f36` | Cards, table containers |
| `--bg-surface-3` | `#1d2942` | Hover rows, nested wells, inputs |
| `--border-subtle` | `#243352` | Hairline borders (1px) |
| `--border-strong` | `#324karm`→ use `#33476f` | Emphasized borders, focus rings base |
| `--text-primary` | `#eef2fb` | Headlines, key numbers |
| `--text-secondary` | `#9fb0d0` | Body, labels |
| `--text-muted` | `#5d6f96` | Captions, SKU, timestamps |
| `--accent` | `#005ab4` | Primary brand blue (KEEP — it is the identity) |
| `--accent-bright` | `#3b8df0` | Hover/active accent, links, focus glow |
| `--gold` | `#e2b65c` | **Warm gold** — reserved for monetary/value metrics & "premium" highlights |
| `--gold-dim` | `#9c7d3a` | Gold borders, subdued gold text |
| `--emerald` | `#34d399` | In-stock / healthy / positive trend |
| `--amber` | `#fbbf24` | Low-stock / watch |
| `--red` | `#f87171` | Out-of-stock / critical / negative trend |

Status surfaces must be **tinted dark glass**, not pastel chips: e.g. low-stock badge = `bg-[#fbbf24]/10 text-[#fbbf24] border border-[#fbbf24]/25`, never `bg-yellow-100`.

> Note on the `#33476f` value: use that exact hex for `--border-strong`. Ignore the typo placeholder in the table.

### 1.3 Typography
- **Family:** keep Inter (already loaded). Add `font-feature-settings: "tnum" 1, "cv11" 1;` on numeric/tabular elements so stat numbers and table quantities align.
- **Scale (apply consistently):**
  - Page title (`h1`): `text-3xl font-black tracking-tight` → `text-primary`
  - Section heading: `text-lg font-bold`
  - Stat number (hero metric): `text-[42px] leading-none font-black tracking-tighter`, tabular-nums
  - Label / eyebrow: `text-[11px] font-bold uppercase tracking-[0.12em] text-muted`
  - Body: `text-sm text-secondary`
  - Caption: `text-[11px] text-muted`
- **Rhythm:** vary spacing. Hero stat cards get generous padding (`p-7`); table rows stay tight (`py-3.5`). Avoid uniform `p-6` everywhere.

### 1.4 Surface & depth language
- Cards: `bg-[#161f36] border border-[#243352] rounded-2xl`. Add a subtle top inner-light: `box-shadow: inset 0 1px 0 0 rgba(255,255,255,0.04)`.
- Elevation on hover: lift `translateY(-2px)` + accent-tinted shadow `0 12px 32px -12px rgba(0,90,180,0.35)`.
- **Atmosphere:** body gets a faint radial glow (top-left accent, bottom-right gold) at very low opacity over the navy base — replace the current light-mode radial gradients in `style.css`.
- One **signature element**: a thin gradient hairline (accent→transparent) under each page `h1`, OR a 1px gradient top-border on stat cards. Pick one and apply it consistently — this is the "not-a-template" tell.

### 1.5 Iconography & logo
- Keep Material Symbols Outlined.
- The faceted gem SVG logo (gold/coral/magenta polygons) is a genuine brand asset — **keep it**, but seat it on a dark tile (`bg-[#0a0e1a] border border-[#243352]`) so it glows against the navy sidebar.

### 1.6 Anti-AI-slop directives (hard rules)
- NO pastel status chips on white. NO pure `#ffffff` card backgrounds anywhere.
- NO three-stop rainbow gradients. Gradients allowed only as: (a) accent→transparent hairlines, (b) very low-opacity atmospheric glows, (c) sparkline area fills.
- NO uniform spacing/radius/shadow across all components — demonstrate hierarchy.
- NO stock illustrations. Empty states use the Material icon set + typography only.
- The hardcoded fake trend text ("+2.5% vs last month") must be **removed or made real** (computed client-side), never left as a lie.

---

## 2. Cross-Cutting Components (build once, reuse)

These should be implemented as repeatable HTML patterns + shared CSS in `style.css`. Since there is no build step and no JS framework, "component" means a consistent markup+class recipe applied identically across pages.

1. **App shell** — unified dark sidebar (`260px`, `bg-[#11182b]`) + header (`h-20`, `bg-[#11182b]/80 backdrop-blur`). The sidebar active state uses an accent left-bar + `bg-[#005ab4]/12 text-[#eef2fb]` and a soft accent glow. Must be visually identical on all 5 protected pages.
2. **Stat card** — eyebrow label, hero number, icon tile, and a footer row that is either a real trend delta (green/red arrow + %) or a mini sparkline. Monetary cards use gold accent.
3. **Sparkline** — pure inline SVG (no library). A small helper `renderSparkline(values, opts)` in a new `frontend/charts.js` returns an SVG string (polyline + soft area fill). Used by dashboard value/quantity cards and insights.
4. **Skeleton loader** — shimmer placeholders (CSS keyframe gradient sweep) that replace ALL "Loading…" text states: skeleton stat cards, skeleton table rows (5 rows), skeleton chart blocks.
5. **Empty state** — centered icon-in-circle + bold line + muted helper line + optional primary CTA. Used by inventory (no items), transactions (no log), forecast (insufficient data), insights.
6. **Badge** — dark-glass status badge (in/low/out) with a leading status dot.
7. **Toast** — replace silent inline reverts with a small bottom-right toast for success/error on mutations (stock adjust, threshold apply, category change). Lightweight, no library.
8. **Page enter animation** — `main` children fade-up (`opacity 0→1`, `translateY(8px→0)`) staggered ~40ms, gated behind `prefers-reduced-motion`.

All animations: compositor-friendly (`transform`/`opacity` only), respect `@media (prefers-reduced-motion: reduce)`.

---

## 3. Per-Page Improvements

### 3.1 `login.html`
**Bug fix (required):** `switchAuthTab()` writes `document.getElementById('auth-subtitle').textContent` but no `#auth-subtitle` element exists — clicking "Sign Up" throws. Add an `#auth-subtitle` element under `#auth-title` (e.g. "Manage your inventory with precision") OR guard the write. Adding the element is preferred since the copy improves the page.
- Redesign as a **split / cinematic dark auth screen**: left = brand panel (navy with atmospheric glow, the gem logo large, a one-line value prop, maybe 3 tiny feature bullets); right = the auth card on `bg-[#161f36]`. On mobile, stack with brand panel collapsing to a slim header.
- Inputs: dark wells (`bg-[#1d2942]`), accent focus glow. Password visibility toggle button must actually toggle `type` (currently decorative) — small, contained improvement.
- Keep all existing IDs (`login-email`, `login-password`, `reg-email`, `reg-password`, `login-msg`, `reg-msg`, `remember`), all `onclick` handlers, and the password regex unchanged.

### 3.2 `dashboard.html`
- Apply dark shell + new stat cards. 4 stat cards: Total Products, Out of Stock (red), Low Stock (amber), Total Value (**gold**).
- **Replace the fake "+2.5%" footer** on each card. If real comparison data isn't available from `getInsights()`, render a small sparkline of a derived series (e.g. recent transaction-volume sourced from `getTransactions()` if cheap), or a meaningful static descriptor — but no fabricated percentages.
- Inventory preview table: dark theme, dark-glass badges, monospaced/tabular quantities, status dot. Keep it read-only (no edit/delete) per existing behavior.
- Alert banners: convert to dark-glass alert rows (red/amber tint, leading icon, subtle left accent bar).
- Skeleton loaders for stat cards + table on first paint.
- Preserve: `loadDashboard()`, `loadInventory()`, all element IDs (`stat-total`, `stat-out`, `stat-low`, `stat-value`, `inventory-body`, `dashboard-alerts`, `pagination-text`), `escHTML`.

### 3.3 `inventory.html`
- Dark theme for the full table + toolbar. Elevate the search/filter UI: a proper toolbar with a search field (icon-prefixed dark well), category filter, and the existing action buttons (Export CSV, Print Report, Manage Categories) restyled as dark secondary buttons; primary "Add Item" as accent.
- Row hover reveals quick stock +/- controls (existing behavior) — restyle as dark icon buttons that slide/fade in.
- Inline category `<select>` → dark-styled select.
- Skeleton rows on load; empty state when no items.
- **Do not change** any JS function names, IDs, modal IDs (`add-modal`, `deduct-modal`, `manage-categories-modal`, `delete-category-confirm-modal`), or the `@media print` `#print-section` mechanism. Verify print rules in `style.css` still hide the right nodes after restyling.
- Modals: restyle to dark glass (`bg-[#161f36]`, backdrop `bg-black/60 backdrop-blur-sm`).

### 3.4 `insights.html`
- This page currently presents analytics as text. Add **data visualization**:
  - A health-score gauge or radial progress (inline SVG) for the overall inventory health score.
  - A horizontal bar / distribution showing in-stock vs low vs out counts (stacked bar, dark with the three status colors).
  - Reorder recommendation list as dark cards with severity-colored left borders.
- Keep all existing data-fetch logic and IDs. Degrade gracefully (empty state) when `getInsights()` returns sparse data.

### 3.5 `forecast.html` (special attention — inconsistent outlier)
**Current state is divergent and partially broken-by-design for theming:** it uses a *minimal* `tailwind.config` (`colors: { brand: '#005ab4' }` only — no `primary`/`surface`/Material tokens), loads the Tailwind CDN **after** the config script, has a different `w-64` sidebar with a different logo, and defines a duplicate local `escHtml` (lowercase) alongside the shared `escHTML`.
- **Normalize this page to match the others:** same `<head>` Tailwind config block ordering as `dashboard.html` (config script BEFORE the CDN `<script src>`), same `260px` dark sidebar + gem logo + header, same nav markup so `initNav('forecast')` highlights correctly.
- Apply dark theme to the forecast cards. Add a small **burn-rate sparkline** per card and a colored urgency meter (days-until-stockout as a horizontal bar: red <7, amber 7–30, emerald >30).
- Keep `loadForecast()`, `renderForecast()`, `applyThreshold()`, `urgencyClass()`, `getForecast()`, `updateItem()` calls, and all IDs (`forecast-grid`, `apply-btn-${idx}`, `apply-msg-${idx}`) intact. The local `escHtml` may stay or be unified to `escHTML` — but if unified, update all call sites in this file.

### 3.6 `transactions.html`
- Dark theme. Transaction log as a dark table or timeline. Change-type badges color-coded (create=accent, stock_in=emerald, stock_out=amber, update=secondary, delete=red) with leading icons.
- Restyle search + type filter as dark toolbar controls. Skeleton + empty state.
- Preserve filter/search JS and IDs.

### 3.7 `add-item.html`
- Dark form. Two-column layout on desktop: form fields left, **live preview card right** that mirrors how the item will appear in inventory (name, category, qty, computed status badge) updating on input.
- Add field hints/helper text (e.g. "Low-stock alerts trigger at or below this quantity") under threshold and price fields.
- Keep form field IDs and submit handler logic intact (edit mode via `sessionStorage` key `iq_editItem` must still work).

### 3.8 `forgot-password.html` & `reset-password.html`
- Apply the same dark auth treatment as `login.html` for consistency. Keep all IDs, `?token=` parsing, and submit handlers unchanged. These are lower priority (Sprint 4) but must not be left light-mode while everything else is dark.

### 3.9 `style.css`
- Replace light-mode body gradients with dark base + atmospheric glow.
- Add: skeleton shimmer keyframes, toast styles, sparkline helpers if any non-inline CSS needed, dark scrollbar styling, reduced-motion block, page-enter stagger.
- Audit `@media print`: print output should be **light/legible on paper** (force white bg, dark text inside `#print-section`) even though the app is dark. Ensure the existing hide rules still target the correct elements after restyle.

---

## 4. Technical Stack & Constraints (hard limits)

- **No build step.** Tailwind via CDN must remain the styling mechanism. No PostCSS, no compiled CSS pipeline.
- **No new npm packages, no bundler, no framework.** Vanilla JS only. Charts/sparklines/gauges = hand-rolled inline SVG (a new `frontend/charts.js` is permitted and must be added to the script-load list of pages that use it, AFTER `utils.js`/`api.js` and before page logic).
- **No CDN chart libraries** (no Chart.js, no ApexCharts). Keeps bundle/CSP small and matches the "no third-party scripts" posture.
- **Do not touch** `config.js`, `api.js` request logic, any `lambda/`, the `notes` file, or auth/session semantics.
- **Preserve every element ID, function name, `onclick` handler, and modal ID** referenced by existing inline scripts. Restyling = classes/markup-wrapping only around the contractually-required hooks.
- Script load order on protected pages stays: `config.js` → `utils.js` → `api.js` → (`charts.js` if used) → page script.
- The Tailwind config block must precede the Tailwind CDN `<script src>` on every page (fix `forecast.html`).
- Respect `prefers-reduced-motion`. Keep animations on `transform`/`opacity`.
- Accessibility: maintain ≥4.5:1 contrast for body text on dark surfaces (the palette above is tuned for this — verify `--text-secondary` on `--bg-surface-2`). Focus-visible rings on all interactive elements.

---

## 5. Sprint Plan (single generation pass, ordered)

The Generator should tackle these in order so the most impactful, most-visible surfaces land first and shared pieces exist before pages consume them.

**Sprint 1 — Foundation & shell**
- Rewrite `style.css`: dark palette CSS variables, atmospheric body, skeleton shimmer, toast, scrollbar, reduced-motion, page-enter, print overrides.
- Establish the unified dark app shell (sidebar + header) and apply to `dashboard.html`.
- Create `frontend/charts.js` with `renderSparkline()` and a `renderRadialGauge()` helper.

**Sprint 2 — Core data pages**
- `dashboard.html`: dark stat cards (gold value card), real/honest trend or sparkline, dark table, skeletons, dark alerts.
- `inventory.html`: dark table + elevated toolbar, dark modals, hover stock controls, skeleton/empty states.

**Sprint 3 — Analytics & forecast**
- `insights.html`: health gauge + distribution bar + reorder cards.
- `forecast.html`: **normalize head/shell to match**, dark cards, burn sparkline + urgency meter.
- `transactions.html`: dark log, color-coded type badges, toolbar.

**Sprint 4 — Auth & forms polish**
- `login.html`: split cinematic auth + **fix `auth-subtitle` bug** + working password toggle.
- `add-item.html`: dark form + live preview + field hints.
- `forgot-password.html` / `reset-password.html`: matching dark auth treatment.

**Definition of done (whole pass):**
- All 9 pages are dark-luxury and visually consistent (identical shell on the 5 protected pages).
- No "Loading…" plain-text states remain; skeletons everywhere.
- No fabricated metrics; the login `auth-subtitle` crash is fixed; forecast page no longer diverges.
- Every existing JS hook (IDs, functions, handlers, modals, print) still works — no console errors on any page.

---

## 6. Evaluation Rubric

Evaluator scores each criterion 0–10. Weighted total out of 10. **Pass threshold: ≥ 7.5 weighted, with no individual criterion below 5, and zero functional regressions (any broken existing flow is an automatic fail regardless of score).**

| # | Criterion | Weight |
|---|-----------|--------|
| 1 | Design Quality | 0.30 |
| 2 | Originality / Anti-Template | 0.20 |
| 3 | Craft & Polish | 0.30 |
| 4 | Functionality Preserved | 0.20 |

### Criterion 1 — Design Quality (0.30)
- Dark luxury palette applied correctly; no white cards, no pastel-on-white chips. (0–3)
- Clear typographic hierarchy: hero numbers vs eyebrows vs body; tabular numerals on metrics. (0–3)
- Depth & rhythm: layered surfaces, non-uniform spacing, signature hairline/atmosphere element present and consistent. (0–2)
- Gold reserved meaningfully for monetary/premium accents; status colors semantic. (0–2)

### Criterion 2 — Originality / Anti-Template (0.20)
- Does NOT read as a default Tailwind dashboard; has a point of view (Bloomberg/Linear terminal feel). (0–4)
- Login is a distinctive split/cinematic screen, not a centered white card. (0–3)
- Insights/forecast feature real inline-SVG data viz (gauge/bars/sparklines), not text. (0–3)

### Criterion 3 — Craft & Polish (0.30)
- Skeleton loaders replace all plain "Loading…" text. (0–3)
- Designed hover/focus/active states; page-enter + micro-animations; reduced-motion respected. (0–3)
- Empty states + error states + toasts are styled and consistent. (0–2)
- Responsive at 375 / 768 / 1024 / 1440 with no overflow; modals/print intact. (0–2)

### Criterion 4 — Functionality Preserved (0.20)
- All existing IDs/functions/handlers/modals present and working; no console errors. (0–5)
- `auth-subtitle` bug fixed; password toggle works; forecast page normalized and `initNav` highlights it. (0–3)
- No backend/contract changes; CSV export & print still produce correct output. (0–2)

### Evaluation method (for the Evaluator)
- Playwright screenshots at 375, 768, 1024, 1440 for: login, dashboard, inventory, insights, forecast, transactions, add-item.
- Check console for errors on each page load and after: switching login↔register, opening each inventory modal, applying a forecast threshold, a stock +/- adjust.
- Verify no element referenced by inline JS was removed (grep the contracted IDs/function names listed in section 3).
- Confirm print preview of inventory renders legibly (light, only `#print-section`).

---

## 7. Risk Notes for the Generator
- The biggest regression risk is renaming/removing an ID or handler during restyle. When in doubt, **wrap, don't replace** the element carrying a JS hook.
- `forecast.html`'s minimal Tailwind config means classes like `text-primary`/`bg-surface` currently do nothing there; after normalizing its config, double-check it still renders (it may suddenly pick up tokens it didn't before).
- The Material color tokens in each `tailwind.config` are a light palette. Prefer explicit arbitrary dark hexes (e.g. `bg-[#161f36]`) over those tokens to avoid accidental light-mode bleed; you may leave the token block in place (harmless) but don't rely on it for the dark look.
- Inline `style.css` `input/select/textarea` rules currently force a *light* well background — these will fight the dark inputs. Update them to the dark palette so form controls don't render light against dark cards.
