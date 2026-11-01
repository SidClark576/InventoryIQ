---
title: "Sentry scrubbing in Lambdas: before_send misses transactions; S3 event keys are URL-encoded"
author: Sidney
date: 2026-10-27
branch: development
cost: { minutes: 218, tokens: 665299 }
id: l-428be770
scope: repo
status: active
src: agent
touches:
  - AGENTS.md
  - lambda/AddItem.py
  - lambda/Authentication.mjs
  - lambda/BulkImport.py
  - lambda/BulkImportAsync.py
  - lambda/CascadeDeleteUser.py
  - lambda/DeleteCategory.py
  - lambda/DeleteItem.py
  - lambda/GetAllItems.py
  - lambda/GetTransactions.py
---

## Decided
- lambda/_logging.py `_scrub_event` drops x-session-token/authorization/cookie headers and redacts invite tokens (url, query_string, breadcrumbs) via `before_send`. Performance tracing is OFF (no traces_sample_rate); `before_send_transaction=_scrub_event` is only a guard.
- lambda/BulkImportAsync.py decodes the S3 key with `urllib.parse.unquote_plus` before splitting out the userID (an email) and before get_object.

## Tried and ruled out
- `before_send` alone (job 007 round 3): Sentry sends transaction events through `before_send_transaction`, not `before_send`, so with traces_sample_rate=1.0 every request still shipped the session JWT and raw invite URL to Sentry.

## Watch out
- Re-enabling tracing needs span/breadcrumb scrubbing too, not just the event request block.
- S3 event `object.key` turns `@` into `%40` and spaces into `+`; comparing it raw to a stored email rejects every real upload (moto tests pass with unencoded keys, so write the test with `%40`).
