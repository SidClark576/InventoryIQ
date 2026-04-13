# Product Specification: InventoryIQ Production Hardening

> Generated from brief: "InventoryIQ Production-Ready Planning Sprint -- 8-week roadmap from live MVP to production-hardened inventory management system"

## Vision

InventoryIQ is a live, AWS serverless inventory management system serving real users. It has working CRUD, multi-user isolation via GSI queries, transaction audit logging, and SNS-based stock alerts. This 8-week roadmap closes every gap between the current MVP and a system businesses can rely on daily: security hardening (weeks 1-2), data integrity and resilience (weeks 3-4), and user-facing power features including barcode scanning, bulk import, and demand forecasting (weeks 5-8).

## Current State Assessment

### Already Implemented and Deployed
- GSI queries on `userID-index` in GetAllItems.py, LowItemInsight.py, GetCategories.py, GetTransactions.py (all per-user reads use GSI, not table scans)
- Ownership verification on UpdateItem.py and DeleteItem.py (403 on userID mismatch)
- Proxy pattern hiding API key from browser (Proxy.py)
- Transaction audit logging on all mutations (AddItem, UpdateItem, DeleteItem)
- SNS alert cooldown (per-user, 24h default)
- Category management with safe reassignment on delete
- DailyAlert.py scheduled email reports

### Sprint 1 Code: Ready but NOT YET DEPLOYED
The following code changes exist in the repository but have NOT been deployed to AWS:
- GSI optimization across GetAllItems.py, GetTransactions.py, LowItemInsight.py, GetCategories.py
- Ownership verification in UpdateItem.py and DeleteItem.py

**First action in Week 1 is deploying Sprint 1 code and creating the required GSI indexes.**

### Critical Gaps (Prioritized)

| # | Category | Problem | Severity |
|---|----------|---------|----------|
| 1 | **LIVE BUG** | `UpdateItem.py` line 56: `response = table.get_item(...)` shadows the `response()` helper function (line 146). All error paths after line 56 crash with `TypeError: 'dict' object is not callable` | **Critical** |
| 2 | Security | No server-side session validation. Anyone who sets `sessionStorage.userEmail` can access that user's data | **Critical** |
| 3 | Security | `AddItem.py` trusts `userID` from request body -- cross-account item injection possible | **Critical** |
| 4 | Security | CORS is `Access-Control-Allow-Origin: *` on all endpoints | **High** |
| 5 | Security | No rate limiting on Authentication.mjs -- unlimited brute-force attempts | **High** |
| 6 | Security | No password complexity requirements | **Medium** |
| 7 | Correctness | `Proxy.py` builds query strings without URL encoding -- emails with `+` break | **Medium** |
| 8 | Correctness | No input validation -- negative quantities, oversized strings accepted | **Medium** |
| 9 | Resilience | Non-atomic writes (item + transaction log are separate DynamoDB calls) | **High** |
| 10 | Resilience | No optimistic locking -- concurrent updates silently overwrite | **Medium** |
| 11 | Observability | Zero structured logging in Python Lambdas | **Medium** |
| 12 | UX | No session expiration -- token persists until tab close | **Low** |
| 13 | Operations | No DynamoDB PITR backup | **Low** |
| 14 | Features | No barcode/SKU scanning | **Feature Gap** |
| 15 | Features | No bulk CSV import | **Feature Gap** |
| 16 | Features | No demand forecasting / reorder intelligence | **Feature Gap** |
| 17 | Features | No forgot-password flow | **Feature Gap** |
| 18 | Features | No multi-location support | **Feature Gap** |

---

## Sprint Plan (8 Weeks)

---

## Sprint 1: Deploy and Verify (Week 1, Days 1-2)

### Goal
Deploy the existing Sprint 1 code (GSI optimization + ownership verification) and fix the live UpdateItem.py bug.

### Task 1.1: Fix UpdateItem.py Variable Shadowing Bug
**Problem:** Line 56 `response = table.get_item(...)` shadows the `response()` helper on line 146. Every error path after line 56 crashes.

**Code Changes:**
- File: `lambda/UpdateItem.py`
- Change: Rename `response` to `result` on line 56 (matching DeleteItem.py's pattern)
- Lines affected: 1 line
- Complexity: Trivial

**Testing:**
- `PUT /items/{nonExistentID}` with valid userID -> returns 404 (not 500 TypeError)
- `PUT /items/{otherUsersItemID}` with wrong userID -> returns 403 (not 500 TypeError)
- `PUT /items/{validID}` with correct userID -> returns 200 with updated item (unchanged behavior)

**Effort:** 15 minutes

### Task 1.2: Create GSI Indexes on DynamoDB Tables
**This is a MANUAL AWS TASK -- no code changes.**

**AWS Console Steps:**
1. DynamoDB -> Tables -> `InventoryIQ` -> Indexes tab -> Create index
   - Partition key: `userID` (String)
   - Sort key: `createdAt` (String)
   - Index name: `userID-index`
   - Projection: ALL
   - Provisioned capacity: match table settings
2. DynamoDB -> Tables -> `InventoryTransactions` -> Indexes tab -> Create index
   - Same configuration: `userID` partition, `createdAt` sort, name `userID-index`, projection ALL

**Wait time:** GSI creation takes 5-15 minutes per table. Status changes from CREATING to ACTIVE.

**Testing:**
- `GET /items?userID=your@email.com` -> returns your items (not empty, not error)
- `GET /transactions?userID=your@email.com` -> returns transactions sorted newest-first
- `GET /insights?userID=your@email.com` -> returns insights data

### Task 1.3: Deploy All Sprint 1 Lambda Functions
**MANUAL AWS TASK -- deploy each modified Lambda.**

**Deploy commands:**
```bash
cd lambda
zip UpdateItem.zip UpdateItem.py && aws lambda update-function-code --function-name UpdateItem --zip-file fileb://UpdateItem.zip
zip DeleteItem.zip DeleteItem.py && aws lambda update-function-code --function-name DeleteItem --zip-file fileb://DeleteItem.zip
zip GetAllItems.zip GetAllItems.py && aws lambda update-function-code --function-name GetAllItems --zip-file fileb://GetAllItems.zip
zip GetTransactions.zip GetTransactions.py && aws lambda update-function-code --function-name GetTransactions --zip-file fileb://GetTransactions.zip
zip LowItemInsight.zip LowItemInsight.py && aws lambda update-function-code --function-name LowItemInsight --zip-file fileb://LowItemInsight.zip
zip GetCategories.zip GetCategories.py && aws lambda update-function-code --function-name GetCategories --zip-file fileb://GetCategories.zip
```

**Testing after deploy:**
- Full smoke test: login, view dashboard, view inventory, add item, edit item, delete item, view transactions, view insights
- Verify ownership: try to delete another user's item by crafting a request with a different itemID -- expect 403

**Effort:** 2 hours (mostly waiting for GSI creation + manual testing)

### Success Criteria for Sprint 1
- [ ] UpdateItem.py error paths return proper HTTP codes (not 500)
- [ ] All per-user reads use GSI queries (CloudWatch shows Query, not Scan)
- [ ] Ownership checks block cross-user mutations with 403
- [ ] All existing user flows work unchanged

---

## Sprint 2: Security Hardening (Weeks 1-2)

### Goal
Close the authentication bypass, lock down CORS, add rate limiting, and add input validation. After this sprint, InventoryIQ is secure enough for multi-user production use.

### Week 1: Authentication and CORS

#### Task 2.1: Server-Side Session Validation (JWT)
**Problem:** No backend validates the session token. Anyone who sets `sessionStorage.userEmail` to another email can access that user's data.

**Solution:** JWT-based authentication. Authentication.mjs signs a JWT on login; Proxy.py validates it on every request and injects the verified userID.

**Code Changes:**

**File: `lambda/Authentication.mjs` (modify)**
- Import `crypto` for HMAC-SHA256 signing (Node.js built-in, no external dependency)
- On successful login: generate JWT with payload `{email, iat, exp}` signed with `JWT_SECRET` env var
- On register: same JWT generation after successful registration
- Return `{token: "<jwt>", email: "<email>"}` instead of `{token: "<uuid>", email: "<email>"}`
- JWT expiration: 8 hours (`exp = iat + 28800`)
- ~40 lines added (JWT sign function + updated response)

**File: `lambda/Proxy.py` (modify)**
- Before forwarding any request, extract `Authorization: Bearer <token>` header
- Validate JWT signature using `JWT_SECRET` env var and `hmac` + `hashlib` (stdlib)
- Check `exp` claim -- return 401 if expired
- Extract `email` from JWT payload, inject as `X-Verified-UserID` header into forwarded request
- For query-string-based endpoints (GET), replace/inject `userID` param with verified email
- For body-based endpoints (POST/PUT/DELETE), the downstream Lambda reads `X-Verified-UserID` header
- Return 401 with `{"error": "Unauthorized"}` if token is missing, invalid, or expired
- ~50 lines added (JWT validation function + header injection)

**File: `lambda/AddItem.py` (modify)**
- Read userID from `event['headers'].get('X-Verified-UserID')` instead of `body.get('userID')`
- Ignore any `userID` in request body
- ~5 lines changed

**File: `lambda/UpdateItem.py` (modify)**
- Read requesting userID from `event['headers'].get('X-Verified-UserID')` instead of `body.get('userID')`
- Ownership check compares against verified header, not body
- ~5 lines changed

**File: `lambda/DeleteItem.py` (modify)**
- Same pattern: read from `X-Verified-UserID` header
- ~5 lines changed

**File: `frontend/api.js` (modify)**
- Add `Authorization: Bearer ${sessionStorage.getItem('iq_token')}` header to all fetch calls
- Remove `userID` from request bodies (server provides it)
- ~15 lines changed

**File: `frontend/login.html` (modify)**
- On login success, store JWT in `sessionStorage.setItem('iq_token', response.token)`
- Continue storing email in `sessionStorage.userEmail` for display purposes
- ~5 lines changed

**File: `frontend/utils.js` (modify)**
- `requireAuth()`: check for `iq_token` in sessionStorage, not just `userEmail`
- Add JWT expiration check: decode payload (base64), check `exp < Date.now()/1000`
- If expired, clear storage and redirect to login with "Session expired" message
- ~15 lines changed

**AWS Manual Tasks:**
- Add `JWT_SECRET` environment variable to `Authentication` Lambda (generate with `openssl rand -hex 32`)
- Add `JWT_SECRET` environment variable to `Proxy` Lambda (same value)
- Both via: Lambda -> Configuration -> Environment variables -> Edit

**Testing:**
1. Login -> verify response includes JWT (not UUID)
2. Open browser console -> `sessionStorage.setItem('userEmail', 'victim@email.com')` -> navigate to inventory -> should get 401 / redirect to login (NOT victim's data)
3. Valid JWT -> all pages work normally
4. Wait 8+ hours (or set short expiry for testing) -> should redirect to login
5. Tamper with JWT payload -> should get 401

**Effort:** 2-3 days
**Dependencies:** None (foundational -- everything depends on this)

#### Task 2.2: Lock Down CORS Origins
**Problem:** `Access-Control-Allow-Origin: *` on all endpoints.

**Code Changes:**
- Files: ALL Lambda files (10 files)
- Change: Replace `'Access-Control-Allow-Origin': '*'` with `'Access-Control-Allow-Origin': os.environ.get('ALLOWED_ORIGIN', '*')`
- Add `'Access-Control-Allow-Credentials': 'true'` header
- ~2 lines per file, 10 files = 20 lines total

**AWS Manual Tasks:**
- Add `ALLOWED_ORIGIN` environment variable to ALL Lambda functions
- Value: `https://main.d5yhjealfqngt.amplifyapp.com`
- 10 Lambda functions to update (AddItem, UpdateItem, DeleteItem, GetAllItems, GetCategories, DeleteCategory, GetTransactions, LowItemInsight, Proxy, Authentication)

**Testing:**
- Open app from production URL -> works normally
- Open browser console on a different domain, try to fetch the API -> CORS error

**Effort:** 2 hours
**Dependencies:** None

### Week 2: Rate Limiting, Validation, Password Strength

#### Task 2.3: Authentication Rate Limiting
**Problem:** Unlimited brute-force login attempts.

**Code Changes:**
- File: `lambda/Authentication.mjs` (modify)
- Add rate limiting logic using DynamoDB Users table
- On failed login: increment counter item `{Email: "rate_limit#<email>", attempts: N, windowStart: ISO, ttl: epoch}`
- After 5 failures in 15 minutes: return 429 `{"error": "Too many login attempts. Try again in 15 minutes."}`
- On successful login: delete the rate limit item
- Add DynamoDB TTL so stale rate limit records auto-expire
- ~40 lines added

**AWS Manual Tasks:**
- Enable TTL on Users table: DynamoDB -> Users -> Additional settings -> Time to Live -> Enable with attribute name `ttl`

**Testing:**
1. Login with wrong password 5 times -> 6th attempt returns 429
2. Wait 15 minutes -> login attempts work again
3. Login with correct password after 3 failures -> succeeds and resets counter
4. Successful login -> verify rate limit item is deleted

**Effort:** 4 hours
**Dependencies:** None

#### Task 2.4: Input Validation Hardening
**Problem:** Negative quantities, negative prices, oversized strings accepted.

**Code Changes:**
- File: `lambda/AddItem.py` (modify)
- File: `lambda/UpdateItem.py` (modify)
- Add validation function (shared via copy -- no shared layer in this architecture):
  ```
  validate_field(field, value, rules) -> (valid: bool, error: str)
  ```
- Validation rules:
  - `quantity`: integer, >= 0
  - `price`: number, >= 0
  - `lowStockThreshold`: integer, >= 1
  - `name`: string, non-empty, max 200 chars
  - `description`: string, max 2000 chars
  - `category`: string, non-empty, max 100 chars
  - `userID`: string, valid email format (basic regex `^[^@]+@[^@]+\.[^@]+$`)
- Return 400 with field-level errors: `{"error": "quantity must be a non-negative integer", "field": "quantity"}`
- ~30 lines added per file

**Testing:**
- `POST /items` with `{quantity: -5}` -> 400
- `POST /items` with `{price: -10}` -> 400
- `POST /items` with `{name: ""}` -> 400
- `POST /items` with `{name: "x" * 201}` -> 400
- `POST /items` with valid data -> 200 (unchanged)

**Effort:** 4 hours
**Dependencies:** None

#### Task 2.5: Password Complexity Requirements
**Code Changes:**
- File: `lambda/Authentication.mjs` (modify)
  - Add validation on register: min 8 chars, at least 1 uppercase, 1 lowercase, 1 digit
  - Return 400 with message: "Password must be at least 8 characters with uppercase, lowercase, and a number"
  - ~10 lines added
- File: `frontend/login.html` (modify)
  - Add inline validation on register form (show/hide error message below password field)
  - ~15 lines added

**Testing:**
- Register with "abc" -> 400 error
- Register with "Abcdef1!" -> success
- Frontend shows validation message before submit

**Effort:** 1 hour
**Dependencies:** None

### Success Criteria for Sprint 2
- [ ] Forged sessionStorage grants no access (401 from Proxy.py)
- [ ] CORS locked to production domain
- [ ] Brute force blocked after 5 failures
- [ ] Invalid input rejected with field-level 400 errors
- [ ] Weak passwords rejected at registration

---

## Sprint 3: Data Integrity and Resilience (Weeks 3-4)

### Goal
Make all database mutations atomic, add optimistic locking for concurrent access, and fix the Proxy.py URL encoding bug.

### Week 3: Atomic Writes

#### Task 3.1: Atomic Transaction Logging with TransactWriteItems
**Problem:** Item mutation and transaction log are separate DynamoDB calls. Partial failure leaves inconsistent state.

**Code Changes:**

**File: `lambda/AddItem.py` (modify)**
- Replace separate `table.put_item()` + `tx_table.put_item()` with:
  ```python
  dynamodb.meta.client.transact_write_items(TransactItems=[
      {'Put': {'TableName': 'InventoryIQ', 'Item': item_data}},
      {'Put': {'TableName': 'InventoryTransactions', 'Item': tx_data}}
  ])
  ```
- ~20 lines changed (restructure write section)

**File: `lambda/DeleteItem.py` (modify)**
- Replace separate `table.delete_item()` + `tx_table.put_item()` with:
  ```python
  dynamodb.meta.client.transact_write_items(TransactItems=[
      {'Delete': {'TableName': 'InventoryIQ', 'Key': {'itemID': {'S': item_id}}}},
      {'Put': {'TableName': 'InventoryTransactions', 'Item': tx_data}}
  ])
  ```
- Note: TransactWriteItems requires raw DynamoDB client format (not resource format). Must convert types.
- ~25 lines changed

**File: `lambda/UpdateItem.py` (modify)**
- TransactWriteItems does not support `UpdateExpression` with `ReturnValues`. Restructure to:
  1. Read existing item (already done)
  2. Merge updates in Python
  3. Put full updated item + Put tx record atomically
- ~30 lines changed (restructure to read-merge-Put pattern)

**Testing:**
- Add item -> verify both InventoryIQ and InventoryTransactions have entries
- Delete item -> verify item gone from InventoryIQ AND transaction logged
- Simulate failure: temporarily break tx table name -> verify item is NOT created (atomic rollback)
- All existing CRUD operations work unchanged from user perspective

**Effort:** 1.5 days
**Dependencies:** Task 1.1 (UpdateItem.py bug fix)

#### Task 3.2: Fix Proxy.py URL Encoding
**Code Changes:**
- File: `lambda/Proxy.py` (modify)
- Replace manual query string construction (line 26-27) with `urllib.parse.urlencode(qs)`
- Add 10-second timeout to `urllib.request.urlopen(req, timeout=10)`
- Add single retry with 500ms delay for 5xx responses
- ~15 lines changed/added

**Testing:**
- Request with `userID=test+user@example.com` -> downstream receives correct email
- Request with `userID=user&admin=true@example.com` -> no query parameter injection
- Kill downstream API -> Proxy returns 504 after 10s timeout (not hang indefinitely)

**Effort:** 2 hours
**Dependencies:** None

### Week 4: Optimistic Locking and Session Expiration

#### Task 3.3: Optimistic Locking on Updates
**Code Changes:**
- File: `lambda/UpdateItem.py` (modify)
- Add `version` field to items (integer, starts at 1)
- In the atomic Put, add `ConditionExpression='attribute_not_exists(itemID) OR version = :expected_version'`
- On `ConditionalCheckFailedException`, return 409 with `{"error": "Item was modified by another user. Please refresh."}`
- Increment version on every update
- ~15 lines added

- File: `lambda/AddItem.py` (modify)
- Set `version: 1` on new items
- ~1 line added

- File: `frontend/api.js` (modify)
- Handle 409 response: show toast "This item was modified. Refreshing..." and reload inventory
- ~10 lines added

- File: `frontend/inventory.html` (modify)
- Pass `version` field through to update calls
- ~5 lines changed

**Testing:**
1. Open two browser tabs on inventory page
2. Edit same item in both tabs (change quantity)
3. Save in tab 1 -> success
4. Save in tab 2 -> 409 with refresh prompt
5. After refresh, tab 2 shows tab 1's values

**Effort:** 4 hours
**Dependencies:** Task 3.1 (atomic writes)

#### Task 3.4: Session Expiration and Auto-Logout
**Code Changes:**
- File: `frontend/utils.js` (modify)
- `requireAuth()` already checks for token (from Task 2.1). Add:
  - Decode JWT payload, check `exp` field
  - If expired, clear sessionStorage, redirect to login with `?expired=true`
- Add periodic check: `setInterval(checkTokenExpiry, 60000)` (check every minute)
- ~20 lines added

- File: `frontend/login.html` (modify)
- Check URL param `?expired=true`, show "Your session has expired. Please log in again." message
- ~5 lines added

**Testing:**
- Set JWT expiry to 1 minute for testing -> verify redirect after 1 minute
- Normal 8-hour expiry works in production

**Effort:** 2 hours
**Dependencies:** Task 2.1 (JWT implementation)

### Success Criteria for Sprint 3
- [ ] All mutations are atomic (both writes succeed or both roll back)
- [ ] Concurrent updates on same item produce 409 (not silent overwrite)
- [ ] Proxy handles special characters in query strings
- [ ] Proxy times out after 10 seconds on hung downstream
- [ ] Sessions expire after 8 hours with clean redirect

---

## Sprint 4: Observability and Operations (Weeks 4-5)

### Goal
Make the system diagnosable and recoverable. Add structured logging, CloudWatch alarms, and backups.

#### Task 4.1: Structured JSON Logging in All Python Lambdas
**Code Changes:**
- Files: ALL 9 Python Lambda files
- Add at top of each file:
  ```python
  import logging
  logger = logging.getLogger()
  logger.setLevel(logging.INFO)
  ```
- Log at entry: `logger.info(json.dumps({"event": "request", "request_id": context.aws_request_id, "method": method, "user_id": user_id}))`
- Log at success: `logger.info(json.dumps({"event": "response", "request_id": context.aws_request_id, "status": 200, "duration_ms": elapsed}))`
- Log at error: `logger.error(json.dumps({"event": "error", "request_id": context.aws_request_id, "error": str(e), "traceback": traceback.format_exc()}))`
- Add `import traceback, time` to each file
- Never log passwords, API keys, or full request bodies
- ~20 lines added per file, 9 files = ~180 lines total

**Testing:**
- Invoke any Lambda -> CloudWatch Logs shows structured JSON entry
- CloudWatch Logs Insights query: `fields @timestamp, request_id, user_id, status | filter event = "request"` -> returns results
- Trigger a 500 error -> CloudWatch shows ERROR entry with traceback

**Effort:** 1 day
**Dependencies:** None

#### Task 4.2: CloudWatch Alarms and Dashboard
**This is a MANUAL AWS TASK -- no code changes.**

**AWS Console Steps:**
1. CloudWatch -> Alarms -> Create alarm:
   - **5xx Error Rate:** Metric = API Gateway 5XXError, threshold > 5 in 5 minutes, notify SNS topic
   - **Lambda Errors:** Metric = Lambda Errors (per function), threshold > 3 in 5 minutes
   - **Lambda Throttles:** Metric = Lambda Throttles, threshold > 0
   - **DynamoDB Consumed RCU:** Alert if > 80% of provisioned capacity
   - **API Gateway 429s:** Metric = 4XXError filtered to 429, threshold > 10 in 5 minutes

2. CloudWatch -> Dashboards -> Create dashboard "InventoryIQ-Production":
   - Widget 1: API Gateway request count (line chart, 5m intervals)
   - Widget 2: Lambda error count by function (stacked area)
   - Widget 3: DynamoDB consumed capacity (InventoryIQ, Users, InventoryTransactions)
   - Widget 4: API Gateway latency (p50, p90, p99)
   - Widget 5: Lambda duration by function (bar chart)

**Testing:**
- Trigger a Lambda error -> alarm fires -> SNS notification received
- Dashboard shows live metrics

**Effort:** 3 hours
**Dependencies:** SNS topic (already exists)

#### Task 4.3: DynamoDB Point-in-Time Recovery
**MANUAL AWS TASK -- no code changes.**

**AWS Console Steps:**
1. DynamoDB -> Tables -> `InventoryIQ` -> Backups -> Point-in-time recovery -> Enable
2. DynamoDB -> Tables -> `Users` -> Backups -> Point-in-time recovery -> Enable
3. DynamoDB -> Tables -> `InventoryTransactions` -> Backups -> Point-in-time recovery -> Enable

**Cost:** ~$0.20/GB/month (negligible for small tables)

**Testing:**
- Verify PITR status shows "Enabled" on all three tables
- Note: no need to test actual restore unless disaster recovery drill is planned

**Effort:** 10 minutes
**Dependencies:** None

#### Task 4.4: Error Message Sanitization
**Code Changes:**
- Files: ALL Lambda files
- Replace `return response(500, {'error': str(e)})` with `return response(500, {'error': 'Internal server error'})`
- Log the real error via structured logging (Task 4.1) but never return it to the client
- Prevents leaking DynamoDB table names, ARNs, or stack traces to attackers
- ~1 line per file, 10 files

**Testing:**
- Trigger an error (e.g., invalid JSON body) -> response says "Internal server error" (not Python traceback)
- CloudWatch logs still contain the full error for debugging

**Effort:** 30 minutes
**Dependencies:** Task 4.1 (logging must be in place first so errors are still diagnosable)

### Success Criteria for Sprint 4
- [ ] Every Lambda invocation produces structured JSON log entry
- [ ] CloudWatch alarms fire on 5xx errors and Lambda failures
- [ ] PITR enabled on all three DynamoDB tables
- [ ] Error responses never leak internal details
- [ ] CloudWatch dashboard shows real-time system health

---

## Sprint 5: Barcode Scanning and SKU Lookup (Weeks 5-6)

### Goal
Add barcode scanning capability so users can scan product barcodes with their phone camera to auto-populate item details. This is the most requested feature gap for inventory management tools.

#### Task 5.1: Barcode Scanner Frontend Component
**Code Changes:**

**File: `frontend/add-item.html` (modify)**
- Add "Scan Barcode" button above the form
- Integrate QuaggaJS (CDN: `https://cdn.jsdelivr.net/npm/@ericblade/quagga2@1.8.4/dist/quagga.min.js`) for browser-based barcode scanning
- On click: open camera modal with live viewfinder
- Support barcode formats: UPC-A, UPC-E, EAN-13, EAN-8, Code 128
- On successful scan: close camera, populate form fields with barcode data
- Fallback: manual barcode number entry field for devices without camera
- ~80 lines added (camera modal HTML + QuaggaJS initialization + scan handler)

**File: `frontend/inventory.html` (modify)**
- Add "Scan to Find" button in the search bar area
- On scan: search inventory for matching barcode/SKU
- ~20 lines added

**File: `frontend/style.css` (modify)**
- Add styles for camera viewfinder modal and barcode overlay
- ~15 lines added

**Testing:**
- Open add-item page on mobile -> tap Scan Barcode -> camera opens
- Scan a UPC barcode -> barcode number appears in form
- Scan in inventory page -> matching item highlighted (or "not found" message)
- Desktop without camera -> manual entry field works

**Effort:** 1 day
**Dependencies:** None

#### Task 5.2: Barcode Data Lookup Lambda
**New File: `lambda/BarcodeLookup.py` (create)**
- New Lambda function for `GET /barcode/{code}`
- Queries Open Food Facts API (`https://world.openfoodfacts.org/api/v2/product/{barcode}`) for product data
- Falls back to UPC Item DB (`https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}`) as secondary source
- Returns: `{name, description, category, barcode, source}`
- Cache results in DynamoDB to avoid repeated external API calls (new `BarcodeCache` table or attribute on InventoryIQ table)
- Rate limit external API calls (Open Food Facts has no key but requests courtesy limits)
- ~80 lines

**AWS Manual Tasks:**
1. Create new Lambda function `BarcodeLookup` in AWS Console
   - Runtime: Python 3.12
   - Handler: `BarcodeLookup.lambda_handler`
   - Timeout: 10 seconds (external API calls)
   - Environment variables: `DYNAMODB_TABLE`, `ALLOWED_ORIGIN`
2. API Gateway -> Resources -> Create `/barcode/{code}` resource -> GET method -> Lambda proxy integration -> BarcodeLookup
3. Deploy to `/prod` stage
4. Add route to proxy: API Gateway -> `/proxy/barcode/{code}` -> Proxy Lambda (or add to existing `{proxy+}` catch-all)

**New File: `frontend/api.js` (modify)**
- Add `lookupBarcode(code)` function that calls `GET /proxy/barcode/{code}`
- ~5 lines added

**Testing:**
- `GET /barcode/0049000006346` (Coca-Cola UPC) -> returns product name and description
- `GET /barcode/0000000000000` (invalid) -> returns 404
- Second call to same barcode -> served from cache (faster response)
- Scan barcode on add-item page -> form auto-fills with product name

**Effort:** 1 day
**Dependencies:** Task 2.1 (JWT -- barcode endpoint needs auth)

#### Task 5.3: Add Barcode/SKU Field to Item Schema
**Code Changes:**
- File: `lambda/AddItem.py` (modify)
  - Accept optional `barcode` field in request body
  - Store in DynamoDB item
  - ~5 lines added
- File: `lambda/UpdateItem.py` (modify)
  - Support updating `barcode` field
  - ~5 lines added
- File: `frontend/add-item.html` (modify)
  - Add barcode field to form (pre-populated by scanner)
  - ~5 lines added
- File: `frontend/inventory.html` (modify)
  - Show barcode column in inventory table (or as detail in expanded row)
  - Include barcode in search filter
  - ~10 lines added

**DynamoDB Schema Change:**
- No table changes needed -- DynamoDB is schemaless. New `barcode` attribute is simply added to items.
- Optional: Create GSI `barcode-index` on InventoryIQ table for barcode lookups (if search-by-barcode needs to be fast)

**Testing:**
- Add item with barcode -> barcode stored and displayed
- Search by barcode number -> item found
- Edit item -> barcode field editable
- Items without barcode -> field shows "N/A" (not error)

**Effort:** 4 hours
**Dependencies:** Tasks 5.1, 5.2

### Success Criteria for Sprint 5
- [ ] Camera-based barcode scanning works on mobile browsers
- [ ] Scanned barcode auto-populates item details from external API
- [ ] Barcode field stored with items and searchable
- [ ] Manual barcode entry works as fallback
- [ ] External API failures handled gracefully (scanner still captures code, just no auto-fill)

---

## Sprint 6: Bulk Import and Export (Weeks 6-7)

### Goal
Enable users to import inventory from CSV files and export filtered/full inventory data.

#### Task 6.1: CSV Bulk Import Lambda
**New File: `lambda/BulkImport.py` (create)**
- New Lambda for `POST /items/import`
- Accepts CSV data in request body (base64-encoded for binary safety)
- Parses CSV with `csv.DictReader`
- Required columns: `name`, `quantity`
- Optional columns: `price`, `category`, `description`, `lowStockThreshold`, `barcode`
- Validates each row using same validation rules as AddItem (Task 2.4)
- Uses `dynamodb.meta.client.batch_write_item()` in batches of 25 (DynamoDB limit)
- Logs one "bulk_create" transaction per import (not per item -- avoids transaction spam)
- Returns summary: `{"imported": 45, "errors": [{"row": 12, "error": "quantity must be non-negative"}], "total": 48}`
- Max 500 items per import (prevent abuse)
- ~120 lines

**AWS Manual Tasks:**
1. Create Lambda function `BulkImport` in AWS Console
   - Runtime: Python 3.12
   - Timeout: 30 seconds (batch processing)
   - Memory: 256 MB (CSV parsing)
   - Environment variables: `DYNAMODB_TABLE`, `TRANSACTIONS_TABLE`, `ALLOWED_ORIGIN`, `JWT_SECRET` (if validating JWT directly) or rely on Proxy
2. API Gateway -> Create `POST /items/import` -> Lambda proxy integration -> BulkImport
3. Increase API Gateway payload limit if needed (default 10MB, sufficient for CSV)

**Testing:**
- Upload CSV with 10 valid rows -> all imported, transactions logged
- Upload CSV with 3 invalid rows -> 7 imported, 3 errors reported with row numbers
- Upload CSV with 501 rows -> rejected with "Maximum 500 items per import"
- Upload CSV with wrong headers -> rejected with "Required column 'name' missing"
- Upload empty CSV -> rejected with "No data rows found"

**Effort:** 1 day
**Dependencies:** Task 2.4 (input validation functions)

#### Task 6.2: Bulk Import Frontend
**File: `frontend/inventory.html` (modify)**
- Add "Import CSV" button next to existing "Export CSV" button
- On click: open modal with:
  - File upload dropzone (drag-and-drop + click to browse)
  - CSV format instructions and downloadable template
  - Preview of first 5 rows after file selection
  - "Import" button to submit
  - Progress indicator during upload
  - Results summary: "Imported 45 items. 3 errors." with expandable error details
- ~100 lines added (modal HTML + JS upload logic)

**New File: `frontend/import-template.csv` (create)**
- Template CSV with headers and 2 example rows
- ~5 lines

**Testing:**
- Drag CSV file onto dropzone -> preview shows first 5 rows
- Click Import -> progress bar -> success message with count
- Inventory table refreshes and shows new items
- Error rows highlighted in results with specific error messages

**Effort:** 1 day
**Dependencies:** Task 6.1 (Lambda endpoint)

#### Task 6.3: Enhanced CSV Export
**File: `frontend/inventory.html` (modify)**
- Enhance existing CSV export to include:
  - Barcode field (from Sprint 5)
  - Date filters (export items created/updated in date range)
  - Category filter (export only selected categories)
  - Option to include transaction history as separate CSV
- ~30 lines modified

**Testing:**
- Export with date filter -> only matching items in CSV
- Export with category filter -> only matching category
- Export all -> same as current behavior
- CSV opens correctly in Excel/Google Sheets

**Effort:** 4 hours
**Dependencies:** None

### Success Criteria for Sprint 6
- [ ] CSV import processes valid files and reports errors per-row
- [ ] Import modal has drag-and-drop, preview, and progress indicator
- [ ] Downloadable CSV template available
- [ ] Export enhanced with filters
- [ ] Bulk imports logged in transaction history

---

## Sprint 7: Demand Forecasting and Smart Reorder (Weeks 7-8)

### Goal
Add predictive inventory intelligence: forecast when items will run out based on historical consumption patterns and recommend reorder quantities.

#### Task 7.1: Demand Forecasting Lambda
**New File: `lambda/DemandForecast.py` (create)**
- New Lambda for `GET /forecast?userID=<email>&itemID=<id>`
- Queries InventoryTransactions for the item's `stock_out` transactions over the past 90 days
- Calculates:
  - **Daily consumption rate:** total `stock_out` quantity / days with activity
  - **Weighted moving average:** recent 30 days weighted 2x vs. older 60 days
  - **Days until stockout:** `current_quantity / daily_consumption_rate`
  - **Reorder point:** `daily_consumption_rate * lead_time_days` (lead time configurable, default 7)
  - **Recommended reorder quantity:** `daily_consumption_rate * reorder_period_days` (default 30)
  - **Confidence level:** based on data volume (< 5 transactions = "low", 5-20 = "medium", 20+ = "high")
- Returns:
  ```json
  {
    "itemID": "...",
    "itemName": "...",
    "currentQuantity": 50,
    "dailyConsumptionRate": 3.2,
    "daysUntilStockout": 15,
    "reorderPoint": 22,
    "recommendedReorderQty": 96,
    "confidence": "high",
    "dataPoints": 45,
    "trend": "increasing"  // "increasing", "decreasing", "stable"
  }
  ```
- ~100 lines

**New File: `lambda/ForecastAll.py` (create)**
- New Lambda for `GET /forecast/all?userID=<email>`
- Runs forecast for ALL user items and returns sorted by urgency (days until stockout ascending)
- Returns top 20 most urgent items
- ~60 lines

**AWS Manual Tasks:**
1. Create Lambda functions `DemandForecast` and `ForecastAll`
   - Runtime: Python 3.12
   - Timeout: 15 seconds
   - Memory: 256 MB
   - Environment variables: `DYNAMODB_TABLE`, `TRANSACTIONS_TABLE`, `ALLOWED_ORIGIN`
2. API Gateway -> Create resources:
   - `GET /forecast` -> DemandForecast
   - `GET /forecast/all` -> ForecastAll
3. Deploy to `/prod` stage

**Testing:**
- Item with 30 stock_out transactions over 90 days -> meaningful forecast with "high" confidence
- Item with 2 stock_out transactions -> forecast with "low" confidence
- Item with 0 stock_out transactions -> "Insufficient data for forecast"
- `GET /forecast/all` -> items sorted by days-until-stockout (most urgent first)

**Effort:** 1.5 days
**Dependencies:** Transaction history must have data (existing feature)

#### Task 7.2: Forecasting Dashboard Page
**New File: `frontend/forecast.html` (create)**
- New page: "Forecasting" accessible from sidebar navigation
- Sections:
  1. **Urgency Overview:** Cards showing items running out in <7 days (red), <14 days (yellow), <30 days (green)
  2. **Forecast Table:** All items with columns: Name, Current Qty, Daily Rate, Days Until Stockout, Reorder Point, Recommended Order, Confidence
  3. **Item Detail:** Click an item to see consumption trend chart (simple bar chart using HTML Canvas or Chart.js CDN)
  4. **Reorder List:** Generate a printable reorder list with all items below their reorder point
- ~200 lines (HTML + JS)

**File: `frontend/utils.js` (modify)**
- Update `initNav()` to include Forecasting link
- ~5 lines

**Files: ALL protected HTML pages (modify)**
- Add "Forecasting" to sidebar navigation
- ~3 lines per file, 6 files = 18 lines

**File: `frontend/api.js` (modify)**
- Add `getForecast(itemID)` and `getAllForecasts()` functions
- ~10 lines

**Testing:**
- Navigate to Forecast page -> see urgency cards and forecast table
- Click an item -> consumption trend chart displays
- Print reorder list -> clean printable format
- Items with no transaction data -> "Insufficient data" message (not error)

**Effort:** 1.5 days
**Dependencies:** Task 7.1 (forecast Lambda)

### Success Criteria for Sprint 7
- [ ] Daily consumption rates calculated from transaction history
- [ ] Days-until-stockout prediction displayed per item
- [ ] Reorder recommendations generated automatically
- [ ] Confidence levels reflect data quality
- [ ] Urgency overview highlights critical items
- [ ] Printable reorder list generated

---

## Sprint 8: Forgot Password and Polish (Week 8)

### Goal
Add password recovery flow, perform final hardening, and prepare for production launch.

#### Task 8.1: Forgot Password Flow
**Code Changes:**

**File: `lambda/Authentication.mjs` (modify)**
- Add handler for `POST /auth/forgot-password`:
  - Generate random 6-digit code (not URL token -- simpler for email)
  - Store `{Email: "reset#<email>", code: hashedCode, ttl: epoch+3600}` in Users table
  - Publish reset code via SNS to user's email
  - Return 200 `{"message": "If this email exists, a reset code has been sent."}`
  - (Always return 200 to prevent email enumeration)
- Add handler for `POST /auth/reset-password`:
  - Accept `{email, code, newPassword}`
  - Verify code matches stored hash and is not expired
  - Validate new password meets complexity requirements (Task 2.5)
  - Update password hash and salt in Users table
  - Delete reset code item
  - Return 200 `{"message": "Password updated successfully"}`
- ~60 lines added

**File: `frontend/login.html` (modify)**
- Add "Forgot Password?" link below login form
- On click: show email input + "Send Reset Code" button
- After code sent: show code input + new password input + "Reset Password" button
- Success: show "Password updated" message and return to login form
- ~50 lines added

**AWS Manual Tasks:**
- None (uses existing SNS topic for email delivery)
- Note: User must have confirmed their SNS subscription to receive the reset code

**Testing:**
1. Click "Forgot Password?" -> enter email -> "Reset code sent" message
2. Check email -> 6-digit code received
3. Enter code + new password -> "Password updated" message
4. Login with new password -> success
5. Use expired code (> 1 hour) -> "Code expired" error
6. Use wrong code -> "Invalid code" error
7. Enter email not in system -> still shows "If this email exists..." (no enumeration)

**Effort:** 1 day
**Dependencies:** Task 2.5 (password complexity)

#### Task 8.2: Final Security Audit
**Checklist (manual review, no code unless issues found):**
- [ ] All Lambda error responses return "Internal server error" (not stack traces)
- [ ] No API keys, ARNs, or table names in any client-facing response
- [ ] JWT secret is at least 32 bytes of entropy
- [ ] All CORS headers point to production domain only
- [ ] Rate limiting tested and confirmed working
- [ ] All Lambda functions have minimal IAM permissions (DynamoDB access only to required tables)
- [ ] API Gateway access logging enabled
- [ ] No `console.log` of sensitive data in Authentication.mjs

**AWS Manual Tasks:**
- API Gateway -> Stages -> prod -> Logs/Tracing -> Enable Access Logging
- IAM -> Review Lambda execution roles -> remove any overly broad permissions

**Effort:** 3 hours
**Dependencies:** All previous sprints

#### Task 8.3: Production Launch Checklist
**Manual verification:**
- [ ] Custom domain configured (optional: replace Amplify subdomain with custom domain)
- [ ] HTTPS enforced on all endpoints
- [ ] DynamoDB PITR enabled on all tables
- [ ] CloudWatch alarms tested and alerting
- [ ] All Lambda functions have appropriate timeout values (not 3s default for new functions)
- [ ] API Gateway throttling configured (per-user if possible)
- [ ] SNS bounce/complaint handling configured
- [ ] README updated with production deployment instructions

**Effort:** 2 hours

### Success Criteria for Sprint 8
- [ ] Password recovery works end-to-end via email
- [ ] Security audit finds zero critical issues
- [ ] Production launch checklist fully green
- [ ] All 8 sprints verified and deployed

---

## Technical Stack

No changes to the core stack:
- **Frontend:** Static HTML/JS/CSS on S3 (Amplify) with Tailwind CSS CDN
- **Backend:** AWS Lambda (Python 3.12 + Node.js 20 ESM)
- **Database:** DynamoDB (existing tables)
- **Messaging:** SNS + SQS (unchanged)
- **API Gateway:** Existing proxy pattern

**New AWS Resources Required:**
| Resource | Sprint | Type |
|----------|--------|------|
| `JWT_SECRET` env var | Sprint 2 | Lambda env var (Authentication + Proxy) |
| `ALLOWED_ORIGIN` env var | Sprint 2 | Lambda env var (all 10 Lambdas) |
| TTL on Users table | Sprint 2 | DynamoDB setting |
| `userID-index` GSI on InventoryIQ | Sprint 1 | DynamoDB GSI |
| `userID-index` GSI on InventoryTransactions | Sprint 1 | DynamoDB GSI |
| CloudWatch alarms (5) | Sprint 4 | CloudWatch |
| CloudWatch dashboard | Sprint 4 | CloudWatch |
| PITR on 3 tables | Sprint 4 | DynamoDB backup |
| `BarcodeLookup` Lambda | Sprint 5 | Lambda function |
| `BulkImport` Lambda | Sprint 6 | Lambda function |
| `DemandForecast` Lambda | Sprint 7 | Lambda function |
| `ForecastAll` Lambda | Sprint 7 | Lambda function |
| API Gateway routes (4 new) | Sprints 5-7 | API Gateway |

**New Frontend Pages:**
| Page | Sprint | Purpose |
|------|--------|---------|
| `forecast.html` | Sprint 7 | Demand forecasting dashboard |

**New Lambda Functions:**
| Function | Sprint | Route | Purpose |
|----------|--------|-------|---------|
| `BarcodeLookup.py` | Sprint 5 | `GET /barcode/{code}` | External barcode data lookup |
| `BulkImport.py` | Sprint 6 | `POST /items/import` | CSV bulk import processing |
| `DemandForecast.py` | Sprint 7 | `GET /forecast` | Per-item demand forecast |
| `ForecastAll.py` | Sprint 7 | `GET /forecast/all` | All-items forecast summary |

---

## Evaluation Criteria

### Security (weight: 0.30)
- Can a user access another user's data by forging sessionStorage? (Must be: NO after Sprint 2)
- Can a user create items under another user's account? (Must be: NO after Sprint 2)
- Can an attacker brute-force passwords? (Must be: NO after Sprint 2)
- Are CORS headers locked to the production domain? (Must be: YES after Sprint 2)
- Do error responses leak internal details? (Must be: NO after Sprint 4)

### Data Integrity (weight: 0.25)
- Are mutation + transaction log writes atomic? (Must be: YES after Sprint 3)
- Do concurrent updates silently overwrite? (Must be: NO after Sprint 3)
- Are invalid inputs rejected? (Must be: YES after Sprint 2)
- Is there a data recovery path? (Must be: YES after Sprint 4)

### Resilience (weight: 0.20)
- Does Proxy.py handle special characters? (Must be: YES after Sprint 3)
- Does Proxy.py handle timeouts? (Must be: YES after Sprint 3)
- Do sessions expire? (Must be: YES after Sprint 3)

### Observability (weight: 0.10)
- Does every Lambda produce structured logs? (Must be: YES after Sprint 4)
- Can issues be diagnosed from CloudWatch? (Must be: YES after Sprint 4)

### Features (weight: 0.15)
- Can users scan barcodes to add items? (Sprint 5)
- Can users bulk import from CSV? (Sprint 6)
- Can users see demand forecasts? (Sprint 7)
- Can users recover forgotten passwords? (Sprint 8)

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| JWT implementation breaks existing sessions | All users logged out | Announce maintenance window; deploy during low-traffic period |
| Barcode external APIs unavailable | Scanner captures code but no auto-fill | Graceful fallback to manual entry; cache results in DynamoDB |
| CSV import with 500 items hits Lambda timeout | Import fails mid-batch | 30s timeout + batch-write-items (25 at a time) completes ~500 items in <10s |
| Demand forecast unreliable with sparse data | Users lose trust in predictions | Confidence levels clearly shown; "insufficient data" for < 3 transactions |
| CORS lockdown breaks local development | Dev workflow interrupted | `ALLOWED_ORIGIN` env var supports comma-separated origins; add localhost for dev |
| Proxy.py JWT validation adds latency | All requests slower by ~5ms | JWT validation is CPU-only (HMAC), no network call; negligible overhead |

---

## Timeline Summary

| Sprint | Weeks | Focus | Key Deliverables |
|--------|-------|-------|-----------------|
| Sprint 1 | Week 1 (Days 1-2) | Deploy + Verify | GSI indexes live, bug fixed, ownership checks active |
| Sprint 2 | Weeks 1-2 | Security | JWT auth, CORS, rate limiting, input validation |
| Sprint 3 | Weeks 3-4 | Data Integrity | Atomic writes, optimistic locking, proxy fixes |
| Sprint 4 | Weeks 4-5 | Observability | Structured logging, CloudWatch alarms, PITR, error sanitization |
| Sprint 5 | Weeks 5-6 | Barcode Scanning | Camera scanning, barcode lookup API, SKU field |
| Sprint 6 | Weeks 6-7 | Bulk Import | CSV import Lambda, drag-and-drop UI, enhanced export |
| Sprint 7 | Weeks 7-8 | Demand Forecasting | Consumption analysis, forecast dashboard, reorder recommendations |
| Sprint 8 | Week 8 | Polish + Launch | Forgot password, security audit, production checklist |

**Total: 8 weeks** for a single developer working part-time (~15 hours/week), or **4 weeks** full-time.
