---
title: Destructive e2e tests must skip unless the app talks to a localhost API
author: Sidney
date: 2026-10-30
branch: feat/ux-polish
cost: { minutes: 1, tokens: 52331 }
id: l-8be804da
scope: repo
status: active
src: agent
touches:
  - scripts/local_api.py
---

## Decided
Playwright runs against whatever serves :8000. Under plain `npm run dev` that app calls the LIVE API (real stores). Any e2e that deletes or changes data (first one: Delete -> Undo, job 016-ux-polish) guards itself: wait for the app's first `/proxy/items` request and `test.skip` unless its hostname is localhost/127.0.0.1 (dev:local sets VITE_API_BASE=http://localhost:3001, Floci + scripts/local_api.py). It creates its own item, never touches existing ones. User chose this 2026-10-31.

## Tried and ruled out
- Always run: would delete/restore real items when run against the live API.
- Unit test only: loses the real Delete -> Undo flow check.
- New env flag/config: not needed; the request hostname already tells local from live.

## Watch out
A skip counts as a pass under plain `npm run dev`; the test only proves anything on `npm run dev:local`. Say so in the build/report.
