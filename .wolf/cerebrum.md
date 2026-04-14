# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-04-12

## User Preferences

- **NO AUTO-DEPLOYMENT:** User handles all AWS Lambda deployments themselves. Never execute `aws lambda` commands or `zip` operations. User said: "I don't want you to deploy it on your own, make a note with that on your memory. Give me the instructions what to do after you make changes on the code" — User confirmed [2026-04-13 14:13]: "I already deployed my Authentication.mjs to AWS. You don't need to upload/deploy it by yourself, put that on memory."
- User wants production-hardening specs to be exhaustive: specific files, exact line numbers for bugs, effort estimates, and clear separation of "manual AWS tasks" vs "code changes"
- Priority ordering for roadmaps: security first, then features, then enterprise polish
- User prefers GAN-style multi-agent workflow: Planner writes spec + rubric, Generator implements, Evaluator scores
- ALWAYS run `/caveman` (full mode) at session start. Every session, every conversation. Non-negotiable.

## Key Learnings

- **Project:** InventoryIQ is a serverless AWS inventory management app (Lambda Python/Node.js, DynamoDB, API Gateway, S3/Amplify, SNS, SQS). No local build step or test suite.
- **Auth model:** Currently sessionStorage-based with no server-side token validation. JWT migration is Sprint 2 priority.
- **Proxy pattern:** Proxy.py injects x-api-key server-side so browser never sees it. Auth endpoints bypass proxy entirely.
- **DynamoDB optimization:** `userID-index` with partition key `userID` and sort key `createdAt` already exists and is used by GetTransactions.py. GetAllItems, GetCategories, and LowItemInsight still use table scans and need migration to the GSI.
- **Transaction logging:** AddItem, UpdateItem, DeleteItem all write to InventoryTransactions after mutations as separate calls. TransactWriteItems migration is Sprint 3.
- **Variable naming in Lambdas:** DeleteItem.py uses `result = table.get_item(...)` correctly without shadowing helper functions. This is the reference pattern.
- **Eval rubric structure:** 5 weighted categories (Security 0.30, Data Integrity 0.25, Resilience 0.20, Observability 0.10, Features 0.15) with sprint-by-sprint pass/fail gates and concrete test scenarios.

## Do-Not-Repeat

- [2026-04-12] Never name a variable the same as a helper function in Python Lambda handlers. UpdateItem.py line 56 used `response = table.get_item(...)` shadowing the `response()` helper at line 146, causing TypeError on error paths. Fix: use `result` instead (matching DeleteItem.py). Always check for shadowing when naming variables.

## Decision Log

- [2026-04-12] JWT auth uses HMAC-SHA256 with Node.js crypto built-in (no jsonwebtoken dependency) to keep Lambda cold start fast and avoid package management.
- [2026-04-12] Barcode scanning uses QuaggaJS via CDN (not npm install), consistent with the no-build-step frontend pattern (Tailwind CDN, Inter font CDN).
- [2026-04-12] Multi-location support intentionally excluded from 8-week plan due to schema complexity. Deferred to post-launch.
- [2026-04-12] Demand forecasting uses weighted moving average of stock_out transactions rather than ML/SageMaker, appropriate for data volume and dependency constraints.