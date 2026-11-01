---
title: Proxy.py switches to direct Lambda invoke via PROXY_MODE env flag; JWT secret from SSM with env fallback
author: Sidney
date: 2026-10-30
branch: fix/proxy-direct-invoke
id: l-f46c2d49
scope: repo
status: active
src: agent
touches:
  - AGENTS.md
  - lambda/Authentication.mjs
  - lambda/Proxy.py
  - scripts/deploy_lambdas.sh
  - scripts/local/rehearse_rollout.sh
  - scripts/local_api.py
  - tests/unit/python/conftest.py
  - tests/unit/python/test_Proxy.py
  - tests/unit/python/test_local_api.py
---

## Decided
- lambda/Proxy.py: PROXY_MODE=invoke calls backend Lambdas with lambda:InvokeFunction (API-Gateway-shaped event); unset = legacy HTTP hop to API Gateway with x-api-key. Live stays HTTP until the user flips the flag after deploy; local dev:local defaults to invoke so local checks test the new path.
- Route table lives once in lambda/_routes.py, shared by Proxy.py and scripts/local_api.py (function name = module name).
- Proxy.py and Authentication.mjs read the JWT secret from SSM SecureString named by JWT_SECRET_PARAM once per cold start, else JWT_SECRET env. Same value, sessions survive the switch.
- Deleting old REST routes, API key, usage plan, API_KEY secret, public /barcode route is a user rollout step, then a later cleanup job removes the HTTP path.

## Tried and ruled out
- Straight cut-over (delete HTTP path now): rollback would need redeploying the old zip.
- Separate route copy inside Proxy.py: two lists drift from local_api.
- SSM-only secret: Lambdas break until the parameter exists; deploy order too fragile.

## Watch out
- Proxy needs lambda:InvokeFunction and ssm:GetParameter (+ kms decrypt for SecureString) before PROXY_MODE=invoke / JWT_SECRET_PARAM are set live.
- frontend already calls /barcode through /proxy; the public /barcode/{code} route is unused by the app.
