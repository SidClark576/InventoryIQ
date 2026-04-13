# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-04-13T01:08:38.359Z
> Files: 71 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `AGENTS.md` — InventoryIQ — Codebase Reference (~1381 tok)
- `CLAUDE.md` — OpenWolf (~4372 tok)
- `notes` (~231 tok)
- `package.json` — Node.js package manifest (~97 tok)
- `playwright.config.ts` (~264 tok)

## .claude/

- `settings.json` (~522 tok)
- `settings.local.json` (~46 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## .playwright-mcp/

- `console-2026-04-07T01-57-12-180Z.log` (~920 tok)
- `console-2026-04-07T02-01-53-684Z.log` (~3362 tok)
- `console-2026-04-07T02-10-56-332Z.log` (~5338 tok)
- `page-2026-04-07T01-57-13-293Z.yml` (~471 tok)
- `page-2026-04-07T01-58-48-380Z.yml` (~498 tok)
- `page-2026-04-07T01-59-23-975Z.yml` (~495 tok)
- `page-2026-04-07T01-59-49-385Z.yml` (~412 tok)
- `page-2026-04-07T01-59-59-061Z.yml` (~495 tok)
- `page-2026-04-07T02-00-07-892Z.yml` (~1174 tok)
- `page-2026-04-07T02-00-17-670Z.yml` (~1046 tok)
- `page-2026-04-07T02-00-23-532Z.yml` (~723 tok)
- `page-2026-04-07T02-01-53-785Z.yml` (~723 tok)
- `page-2026-04-07T02-03-06-398Z.yml` (~3016 tok)
- `page-2026-04-07T02-03-11-387Z.yml` (~723 tok)
- `page-2026-04-07T02-10-56-563Z.yml` (~471 tok)
- `page-2026-04-07T02-11-05-469Z.yml` (~1173 tok)
- `page-2026-04-07T02-11-10-947Z.yml` (~1344 tok)
- `page-2026-04-07T02-11-19-161Z.yml` (~722 tok)
- `page-2026-04-07T02-12-17-136Z.yml` (~3012 tok)
- `page-2026-04-07T02-12-21-856Z.yml` (~722 tok)
- `page-2026-04-07T02-14-41-934Z.yml` (~4340 tok)
- `page-2026-04-07T02-14-49-762Z.yml` (~748 tok)
- `page-2026-04-07T02-15-01-158Z.yml` (~762 tok)
- `page-2026-04-07T02-15-10-853Z.yml` (~4340 tok)
- `page-2026-04-07T02-15-22-379Z.yml` (~745 tok)
- `page-2026-04-07T02-15-31-510Z.yml` (~2774 tok)
- `page-2026-04-07T02-15-37-396Z.yml` (~4340 tok)
- `page-2026-04-07T02-15-53-601Z.yml` (~4342 tok)
- `page-2026-04-07T02-15-59-551Z.yml` (~746 tok)
- `page-2026-04-07T02-16-08-215Z.yml` (~2881 tok)
- `page-2026-04-07T02-16-12-698Z.yml` (~4344 tok)
- `page-2026-04-07T02-16-18-255Z.yml` (~742 tok)
- `page-2026-04-07T02-16-26-416Z.yml` (~2933 tok)

## docs/

- `InventoryIQ_Guided_Lab.md` — 🧪 Guided Lab: Building InventoryIQ on AWS (~14619 tok)
- `stitch_design.html` — InventoryIQ | Digital Curator (~4650 tok)

## frontend/

- `add-item.html` — InventoryIQ | Add Asset (~3755 tok)
- `api.js` — Returns standard headers for proxied API requests. (~1482 tok)
- `config.js` — Declares CONFIG (~76 tok)
- `dashboard.html` — InventoryIQ | Dashboard (~4765 tok)
- `index.html` (~30 tok)
- `insights.html` — InventoryIQ | Insights (~3078 tok)
- `inventory.html` — InventoryIQ | Inventory (~9546 tok)
- `login.html` — InventoryIQ | Login (~3250 tok)
- `style.css` — Styles: 7 rules, 1 media queries (~454 tok)
- `transactions.html` — InventoryIQ | Transactions (~3215 tok)
- `utils.js` — requireAuth: initNav, handleLogout (~245 tok)

## gan-harness/

- `eval-rubric.md` — Evaluation Rubric: InventoryIQ 8-Week Production Hardening (~3657 tok)
- `spec.md` — Product Specification: InventoryIQ Production Hardening (~11256 tok)

## lambda/

- `AddItem.py` — Initialize DynamoDB tables (~1681 tok)
- `Authentication.mjs` — Exports handler (~3060 tok)
- `DailyAlert.py` — Initialize AWS service clients at module level (outside the handler) (~3370 tok)
- `DeleteCategory.py` — Initialize DynamoDB with inventory table (~1163 tok)
- `DeleteItem.py` — Initialize DynamoDB tables for inventory and transaction logging (~1338 tok)
- `GetAllItems.py` — Initialize DynamoDB resource and get the inventory table (~964 tok)
- `GetCategories.py` — Initialize DynamoDB with inventory table (~1048 tok)
- `GetTransactions.py` — Initialize DynamoDB with transactions table (~1112 tok)
- `LowItemInsight.py` — Initialize AWS services: (~4040 tok)
- `Proxy.py` — base64url_decode, verify_jwt, lambda_handler (~1264 tok)
- `UpdateItem.py` — Initialize DynamoDB tables at module level so they are reused across warm Lambda invocations (~2486 tok)

## tests/e2e/auth/

- `debug-api.spec.ts` — Declares responses (~579 tok)
- `login.spec.ts` — Declares testEmail (~1613 tok)
- `register.spec.ts` — Declares testEmail (~1234 tok)

## tests/pages/

- `LoginPage.ts` — Exports LoginPage (~1008 tok)
