---
title: migrate_orgs --apply breaks old-app edits (not lists) until new frontend ships
author: Sidney
date: 2026-10-29
branch: development
cost: { minutes: 119, tokens: 1653975 }
id: l-0cf9057b
scope: repo
status: active
src: agent
touches:
  - site/404.html
  - site/README.md
  - site/delete-account/index.html
  - site/favicon.svg
  - site/fonts/bricolage-grotesque-latin-ext-standard-normal.woff2
  - site/fonts/bricolage-grotesque-latin-standard-normal.woff2
  - site/index.html
  - site/netlify.toml
  - site/og.jpg
  - site/privacy/index.html
---

## Decided
Live rollout order: (1) deploy all Lambdas incl. new Orgs/OrgMembers/OrgInvites + API routes, (2) `scripts/migrate_orgs.py --apply`, (3) release the new frontend right after, (4) `--apply` again, (5) check with the store owner. Rehearsed 2026-10-29 on Floci with a copy of the live store (107 items, 150 txs): org mode afterwards showed 106 active items, same itemIDs and same stock total as prod; the rerun stamped 0.

## Watch out
- After stamping, the old frontend (sends no X-IQ-Org) can still LIST items: legacy reads use userID-index in `lambda/_org.py:list_scoped_items`. EDITS fail with 403 "item is outside this organization" because `item_in_scope` requires a matching org_id once orgID is set. So steps 2 and 3 must happen together.
- Between steps 1 and 3, old-app adds are written without orgID; the second `--apply` stamps them.
- Run migrate_orgs locally with AWS_PROFILE unset, not empty (`AWS_PROFILE=` raises ProfileNotFound).
