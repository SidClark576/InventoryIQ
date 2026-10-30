---
title: "Browser checks on dev:local: agent-browser fill can't set date inputs, and local_api.py keeps old Lambda code"
author: Sidney
date: 2026-10-30
branch: feat/item-expiry-alerts
cost: { minutes: 12, tokens: 211273 }
id: l-33852d26
scope: repo
status: active
src: agent
touches:
  - factory/jobs/015-item-expiry-alerts/rounds/1/build.md
  - scripts/local_api.py
---

## Decided
- To set an `<input type="date">` (e.g. `#n-expires`, `#e-expires` in AddItemForm.tsx / ItemEditForm.tsx) from agent-browser, use eval with the native setter: `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'YYYY-MM-DD')`, then dispatch a bubbling `input` event. React picks it up and the real save path runs.

## Tried and ruled out
- `agent-browser fill "#n-expires" 2026-11-29`, `type`, and `keyboard type 11292026` all leave the value empty (job 015).

## Watch out
- `scripts/local_api.py` imports each Lambda module once and keeps it in `sys.modules`. After editing `lambda/*.py`, restart just that process (port 3001) before a browser check, or requests run the old code. `kill` needs the sandbox turned off.
- The 2 pytest failures in job 015 were the tests written first (expected) plus one date mistake in the new test. They had nothing to do with AddItemForm.tsx.
