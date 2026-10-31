---
title: Pre-launch backend work must stay near-$0; live API has no authorizer and Lambda concurrency is 10
author: Sidney
date: 2026-10-30
branch: feat/item-expiry-alerts
cost: { minutes: 16, tokens: 117477 }
id: l-7346b980
scope: repo
status: active
src: agent
touches:
  - docs/backend-hardening-plan.md
  - factory/backlog.md
  - lambda/Proxy.py
  - scripts/local_api.py
  - AGENTS.md
---

## Decided
- No users yet, so backend hardening (docs/backend-hardening-plan.md) only takes $0 steps: stage throttles, arm64/256MB, deletion protection, least-privilege IAM, free CloudWatch alarms, SSM SecureString for JWT_SECRET.
- Fix the double hop by having lambda/Proxy.py call backend Lambdas with lambda:InvokeFunction (same event shape scripts/local_api.py builds), then delete the backend /prod routes, InventoryIQ-Key, the usage plan and the API_KEY secret.

## Tried and ruled out
- WAF, GuardDuty, CloudTrail trail, AWS Backup plan, provisioned concurrency, HTTP API rewrite: each adds a monthly fee or a rewrite; revisit at launch (table in the plan).
- Attaching a cached TOKEN authorizer instead of direct invoke: caching would delay member revoke, which Proxy's live OrgMembers lookup makes instant.

## Watch out
- Live audit 2026-10-31: InventoryIQ-API has 0 authorizers; backend routes are auth NONE + API key and trust x-iq-user/org/role headers. Authorizer.mjs in AGENTS.md is NOT deployed.
- Account Lambda concurrency limit is 10 (already throttling); each request uses 2 (Proxy + handler).
- Usage plan quota 10000/day sits on the single key Proxy uses for every user.
