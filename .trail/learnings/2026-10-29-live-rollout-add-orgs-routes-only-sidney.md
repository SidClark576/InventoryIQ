---
title: "Live rollout: add /orgs routes only together with migrate_orgs --apply"
author: Sidney
date: 2026-10-29
branch: development
cost: { minutes: 1, tokens: 0 }
id: l-e6e06845
scope: repo
status: active
replaces: l-0cf9057b
src: agent
touches:
  - scripts/migrate_orgs.py
  - frontend/src/api.ts
  - scripts/deploy_lambdas.sh
---

## Decided
Rollout order for the org migration: (1) update the existing Lambdas and create the Orgs/OrgMembers/OrgInvites functions WITHOUT adding API Gateway routes; (2) in one sitting run `scripts/migrate_orgs.py --apply`, then add the /orgs, members, invites and org-invites routes and redeploy the prod stage, then run `--apply` again; (3) merge development → main afterwards. Rehearsed on Floci with a copy of the live store: after the migration, org mode shows the same active items, itemIDs and stock total as prod.

## Watch out
- `ensureOrgContext` in frontend/src/api.ts calls GET /orgs on every load and switches to org mode when it succeeds. Any frontend with that code goes into org mode as soon as the /orgs route exists; over unstamped data that shows 0 items.
- After stamping, an app in legacy mode (no X-IQ-Org) can still LIST items (`_org.list_scoped_items` uses userID-index), but edits get 403 from `item_in_scope`. So migrate first, then add the routes straight away.
- `scripts/deploy_lambdas.sh` zips `<Name>.py`; a function whose handler is `lambda_function.lambda_handler` needs its handler set to `<Name>.lambda_handler` in the same deploy.
- Run migrate_orgs locally with AWS_PROFILE unset, not empty (`AWS_PROFILE=` raises ProfileNotFound).
