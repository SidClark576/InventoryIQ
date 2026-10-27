---
title: "Report currency comes from device region (Intl locale/time zone), not IP lookup"
author: Sidney
date: 2026-10-27
branch: main
cost: { minutes: 138, tokens: 979152 }
id: l-94d6ba04
scope: repo
status: active
src: agent
touches:
  - docs/PRD-mobile-app-launch.md
  - frontend/index.html
  - frontend/public/theme-init.js
  - frontend/src/api.ts
  - frontend/src/app/App.tsx
  - frontend/src/app/AppLayout.tsx
  - frontend/src/app/inventory-store.tsx
  - frontend/src/app/use-stock-actions.ts
  - frontend/src/components/barcode-scan-dialog.tsx
  - frontend/src/components/error-boundary.tsx
---

## Decided
Stock report and CSV export pick the currency from the device/browser region (Intl locale, Manila time zone → PHP, US → USD, other countries their local currency). Applies to frontend/src/screens/stock/PrintReport.tsx and frontend/src/screens/stock/export.ts. "Stock in" on the report counts only restocks ("Received" notes), not upward count fixes.

## Tried and ruled out
- Geo-IP lookup: needs a third-party service, must be listed in the privacy policy (site/privacy), fails offline and behind VPN.
- Per-store currency setting: the launch PRD's long-term design (docs/PRD-mobile-app-launch.md), but it needs a backend change; deferred.

## Watch out
When per-store currency ships, it should replace the device-region guess, so a store's report doesn't change currency when the owner travels.
