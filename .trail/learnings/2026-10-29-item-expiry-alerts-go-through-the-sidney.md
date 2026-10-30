---
title: "Item expiry alerts go through the existing SNS topic, not SES or per-user SMS"
author: Sidney
date: 2026-10-29
branch: feat/item-expiry-alerts
cost: { minutes: 4, tokens: 121814 }
id: l-03eba920
scope: repo
status: active
src: agent
touches:
  - lambda/DailyAlert.py
---

## Decided
Item expiry notifications (job 015, feat/item-expiry-alerts) reuse the SNS topic path from lambda/DailyAlert.py: email and SMS recipients are that topic's subscriptions set in the AWS console. One optional expiry date per item; a daily check covers items expiring within 7 days and items already expired; each item is notified once on entering the window and once when it expires, and changing the date re-arms both.

## Tried and ruled out
- SES email to org owners/admins: SES is still in sandbox, so only verified addresses would receive it.
- Per-user email + SMS preferences: needs phone-number UI, consent, and an SNS SMS origination number / 10DLC registration; too big for this job.
- Per-batch dates, CSV import/export of the date, a configurable warning window: out of scope for now.

## Watch out
One SNS topic covers every store (DailyAlert scans all items), so whoever is subscribed sees expiring items from all stores. Per-store recipients need a different channel later.
