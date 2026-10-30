---
title: Expiry alert once-per-state tracking lives on the item as the expiresAt value it was sent for
author: Sidney
date: 2026-10-29
branch: feat/item-expiry-alerts
cost: { minutes: 5, tokens: 168824 }
id: l-58b75a4f
scope: repo
status: active
src: agent
touches:
  - factory/jobs/015-item-expiry-alerts/spec.v1.md
  - lambda/DailyAlert.py
  - scripts/local_api.py
---

## Decided
Job 015 spec (factory/jobs/015-item-expiry-alerts/spec.v1.md): DailyAlert.py marks each reported item with `expirySoonAlertedFor` / `expiredAlertedFor` = the `expiresAt` string it alerted on. "Already notified" is `flag == expiresAt`, so changing the date re-arms both with no UpdateItem change. Flags are written after a successful SNS publish and never touch `version`, so UpdateItem's If-Match lock is unaffected. DailyAlert also starts skipping `deletedAt` rows (it never did for stock sections).

## Tried and ruled out
- Sentinel rows like `LowItemInsight._should_send_alert` (`alert_meta#` + `userID='__system__'`): extra rows and reads, and every scan must exclude them.
- Stateless "alert only at exactly 7 and 0 days left": misses items created inside the window and any skipped daily run.

## Watch out
- `lambda/DailyAlert.py` only scanned before; the live Lambda role needs `dynamodb:UpdateItem` on `InventoryIQ` when this ships (user deploys).
- `scripts/local_api.py` ROUTES has no DailyAlert route; locally it runs via direct `lambda_handler` call or the moto test, not the dev server.
