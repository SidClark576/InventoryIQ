# Live AWS inventory (profile `inventoryiq`)

Captured 2026-10-04 via `AWS_PROFILE=inventoryiq` (account `023202272390`, region `us-east-1`).
Role: `OrganizationAccountAccessRole`. API id matches [`frontend/src/config.ts`](../frontend/src/config.ts): `d1g2j27343`.

Point Cursor AWS MCP at this profile with workspace [`.cursor/mcp.json`](../.cursor/mcp.json) / [`.mcp.json`](../.mcp.json) (`AWS_PROFILE=inventoryiq`). Reload MCP after changing those files. Re-run `scripts/aws_inventory.sh` to refresh.

## Account

| Field | Value |
|---|---|
| Account | `023202272390` |
| Region | `us-east-1` |
| API Gateway | `InventoryIQ-API` (`d1g2j27343`) |
| Frontend | Netlify `https://theinventoryiq.netlify.app` |

## Lambdas deployed

BarcodeLookup, RestoreItem, GetTransactions, DeleteCategory, Authentication, LowItemInsight, Proxy, AddItem, GetAllItems, DeleteItem, GetCategories, DailyAlert, CascadeDeleteUser, UpdateItem, PurgeDeletedItems.

**Removed 2026-10-05:** Lambda `Suppliers` (deleted). Lambda `Forecast` was already absent. Source files `lambda/Suppliers.py` and `lambda/Forecast.py` are gone.

**In repo, not deployed:** `Orgs`, `OrgMembers`, `OrgInvites`, `BulkImport`, `BulkImportAsync`, `Authorizer`.

## DynamoDB tables deployed

AuthAttempts, BarcodeCache, IdempotencyKeys, InventoryIQ, InventoryTransactions, PasswordResets, Sessions, Users.

**Removed 2026-10-05:** DynamoDB table `Suppliers` (deleted).

**In repo, not created:** `Organizations`, `OrgMembers`, `OrgInvites`.

`InventoryIQ` GSI today: `userID-index` only. **`orgID-index` is not on the live table.** Create it (and the org tables) with `scripts/provision_org_infra.py --apply` before relying on org-scoped queries.

## How to refresh

```bash
AWS_PROFILE=inventoryiq AWS_REGION=us-east-1 bash scripts/aws_inventory.sh
```
