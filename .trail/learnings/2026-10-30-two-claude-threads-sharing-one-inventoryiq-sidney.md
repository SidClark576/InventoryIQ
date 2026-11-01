---
title: Two Claude threads sharing one InventoryIQ checkout race on branch switches and factory jobs
author: Sidney
date: 2026-10-30
branch: feat/ux-polish
cost: { minutes: 9, tokens: 113446 }
id: l-8df6dc1d
scope: repo
status: active
src: agent
touches:
  - docs/backend-hardening-plan.md
  - docs/brand/v2/a-tag.svg
  - docs/brand/v2/b-sign.svg
  - docs/brand/v2/c-slice.svg
  - docs/brand/v2/d-focus.svg
  - docs/brand/v2/e-tally.svg
  - docs/brand/v2/f-checked.svg
  - docs/brand/v2/g-gap.svg
  - docs/brand/v2/gen/g-gap-gen-1.png
  - docs/brand/v2/gen/g-gap-gen-2.png
---

## Decided
- Run parallel work (e.g. a backend /factory job while a UI thread runs its own) in a separate git worktree, not the shared checkout at /Users/sidneyordonia/Documents/InventoryIQ.

## Tried and ruled out
- Committing pending work then running `fctl.py start-branch` in the shared checkout: the UI thread's /factory had already switched to feat/ux-polish, so the commits (stock-report columns, docs plans) landed on feat/ux-polish instead of feat/item-expiry-alerts, and start-branch refused because job 016-ux-polish owned the checkout.

## Watch out
- factory allows one open job per checkout; a second thread's job blocks yours.
- Check `git branch --show-current` immediately before any commit when another thread is active; branch can change between your checks.
