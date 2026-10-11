# InventoryIQ

Multi-tenant inventory app. The frontend is a Vite TypeScript build published on **Netlify** (`https://theinventoryiq.netlify.app`). Backend is AWS Lambda + API Gateway + DynamoDB in `us-east-1` (account `023202272390`, profile `inventoryiq`).

## Stack

- Frontend: Vite TypeScript in `frontend/src`, HTML pages in `frontend/`. Netlify runs `npm run build` and publishes `frontend/dist` ([`netlify.toml`](netlify.toml))
- API: `https://d1g2j27343.execute-api.us-east-1.amazonaws.com/prod/proxy`
- Auth: stateless HS256 JWT (`X-Session-Token`)
- Data: DynamoDB (see [ARCHITECTURE.md](ARCHITECTURE.md))

## Local

```bash
npm install
npm run dev          # Vite on http://localhost:8000
npm run build        # typecheck + production build → frontend/dist
```

Playwright (needs `.env.test` — copy [`.env.example`](.env.example)):

```bash
npx playwright test
```

## AWS

Use profile `inventoryiq` (assumes `OrganizationAccountAccessRole` in `023202272390`). Cursor MCP is pointed at that profile in [`.cursor/mcp.json`](.cursor/mcp.json).

```bash
AWS_PROFILE=inventoryiq bash scripts/aws_inventory.sh
python3 scripts/provision_org_infra.py          # dry-run
# python3 scripts/provision_org_infra.py --apply
bash scripts/deploy_lambdas.sh                  # prints zip + update-function-code
```

Do not auto-deploy from CI. Package locally, then run the printed `aws lambda update-function-code` commands.

## Docs

- [AGENTS.md](AGENTS.md) — conventions
- [ARCHITECTURE-ESSENTIALS.md](ARCHITECTURE-ESSENTIALS.md) — production-failure rules
- [docs/aws-live-inventory.md](docs/aws-live-inventory.md) — live account snapshot
