---
title: Printed stock report shows Category per row and keeps the category headings; Size column is labelled Description
author: Sidney
date: 2026-10-30
branch: feat/item-expiry-alerts
cost: { minutes: 3, tokens: 116748 }
id: l-0d442902
scope: repo
status: active
src: agent
touches:
  - AGENTS.md
  - ARCHITECTURE.md
  - frontend/src/api.ts
  - frontend/src/app/use-stock-actions.ts
  - frontend/src/components/item-sheet/AddItemForm.tsx
  - frontend/src/components/item-sheet/ItemEditForm.tsx
  - frontend/src/components/item-sheet/ItemPanel.tsx
  - frontend/src/components/status-badge.tsx
  - frontend/src/lib/dashboardStats.ts
  - frontend/src/lib/format.ts
---

## Decided
- The printed "Inventory of Stocks" sheet (frontend/src/screens/stock/PrintReport.tsx) and the CSV (frontend/src/screens/stock/export.ts) share REPORT_HEADERS in frontend/src/lib/stock-report.ts: Item, Category, Description, Price, Starting stock, Stock in, Stock now. The owner asked for the category on every printed row and for "Size" to be renamed "Description" (the column always showed item.description).
- The "CAN GOODS:" group heading rows stay as well as the per-row Category column, so a row still reads correctly if it is cut out or copied on its own.

## Tried and ruled out
- Dropping the group headings for one flat table: rejected, because owners already read the paper sheet by section.
- Changing the print sheet only and leaving the CSV alone: rejected, because it would need a second header list and the two could drift apart.

## Watch out
- The add and edit item forms (AddItemForm.tsx, ItemEditForm.tsx) still label the field "Size / description". That was out of scope for this change.
- PrintReport right-aligns the columns from index 3 on (Price onward). Moving a column means updating that index.
