# Evaluation Rubric: InventoryIQ 8-Week Production Hardening

## Scoring Scale
Each criterion is scored 0-10. Final score = weighted sum.

---

## 1. Security (weight: 0.30)

| Score | Criteria |
|-------|----------|
| 0-2 | No ownership checks; cross-user mutation possible; no server-side session validation |
| 3-4 | Ownership checks exist but sessionStorage forgery still grants access; CORS still `*` |
| 5-6 | JWT auth on login + Proxy.py validates token; ownership checks on all write endpoints; CORS locked to production domain |
| 7-8 | JWT + ownership + rate limiting (5 failures/15min) + password complexity (8+ chars, mixed case, digit) + input validation rejects negative qty/price |
| 9-10 | Full JWT auth + CORS lockdown + rate limiting + password complexity + input validation + error sanitization (no stack traces leaked) + forgot-password flow prevents email enumeration |

**Test Scenarios:**

Sprint 1 (Deploy + Verify):
- `PUT /items/{nonExistentID}` with valid userID -> returns 404 (not 500 TypeError from shadowing bug)
- `PUT /items/{otherUsersItemID}` with wrong userID -> returns 403
- `DELETE /items/{otherUsersItemID}` with your own userID -> returns 403 or 404

Sprint 2 (Security Hardening):
- Open browser console -> `sessionStorage.setItem('userEmail', 'victim@email.com')` -> navigate to inventory -> must get 401 / redirect to login (NOT victim's data)
- Valid JWT -> all pages work normally
- Tamper with JWT payload (change email claim) -> must get 401
- Expired JWT -> redirect to login with "Session expired" message
- CORS: fetch from different domain -> CORS error (not `Access-Control-Allow-Origin: *`)
- Login with wrong password 5 times -> 6th attempt returns 429
- Login with wrong password 3 times, then correct password -> succeeds and resets counter
- Wait 15 minutes after lockout -> login attempts work again
- `POST /items` with `{name: "x", quantity: -5}` -> returns 400 with field-level error
- `POST /items` with `{name: "x", price: -10}` -> returns 400
- `POST /items` with `{name: ""}` -> returns 400
- `POST /items` with `{name: "x" * 201}` -> returns 400
- Register with password "abc" -> returns 400 with complexity message
- Register with password "Abcdef1!" -> succeeds

Sprint 8 (Forgot Password):
- Click "Forgot Password?" -> enter email -> "If this email exists, a reset code has been sent."
- Enter valid code + new password -> "Password updated" message
- Enter expired code (> 1 hour) -> "Code expired" error
- Enter wrong code -> "Invalid code" error
- Enter non-existent email -> still shows generic success message (no enumeration)

---

## 2. Data Integrity (weight: 0.25)

| Score | Criteria |
|-------|----------|
| 0-2 | Non-atomic writes; no locking; item and transaction log are separate calls |
| 3-4 | Some mutations use TransactWriteItems but not all three (AddItem, UpdateItem, DeleteItem) |
| 5-6 | All three mutation Lambdas use TransactWriteItems for atomic item + transaction writes |
| 7-8 | Atomic writes + optimistic locking via `version` field and ConditionExpression on UpdateItem |
| 9-10 | Full atomicity + optimistic locking + frontend handles 409 conflict gracefully + all inputs validated before write |

**Test Scenarios:**

Sprint 3 (Atomic Writes):
- Add item -> verify both InventoryIQ and InventoryTransactions have entries (atomic)
- Delete item -> verify item gone from InventoryIQ AND transaction logged
- Simulate failure: temporarily break transaction table name -> verify item is NOT created (atomic rollback)
- All existing CRUD operations work unchanged from user perspective

Sprint 3 (Optimistic Locking):
- Open two browser tabs on inventory page
- Edit same item in both tabs (change quantity)
- Save in tab 1 -> success (200)
- Save in tab 2 -> 409 with "Item was modified by another user. Please refresh."
- After refresh, tab 2 shows tab 1's values
- New items start with `version: 1`

Sprint 2 (Input Validation):
- `POST /items` with valid data -> 200 (unchanged behavior)
- `PUT /items/{id}` with `{quantity: -1}` -> 400
- `PUT /items/{id}` with `{lowStockThreshold: 0}` -> 400
- `POST /items` with `{description: "x" * 2001}` -> 400
- Email format validation: `{userID: "not-an-email"}` -> 400

---

## 3. Resilience (weight: 0.20)

| Score | Criteria |
|-------|----------|
| 0-2 | Proxy.py has URL encoding bugs; no timeout; sessions never expire |
| 3-4 | Proxy URL encoding fixed with `urllib.parse.urlencode()`; timeout still missing |
| 5-6 | Proxy URL encoding + 10-second timeout on `urlopen()` |
| 7-8 | URL encoding + timeout + single retry for 5xx + sessions expire after 8 hours with clean redirect |
| 9-10 | Full proxy hardening + session expiration + periodic expiry check (every 60s) + expired token shows friendly message on login page |

**Test Scenarios:**

Sprint 3 (Proxy Fixes):
- Request with `userID=test+user@example.com` -> downstream receives correctly encoded parameter
- Request with `userID=user&admin=true@example.com` -> no query parameter injection
- Kill downstream API -> Proxy returns 504 after 10s timeout (not hang indefinitely)
- Downstream returns 503 -> Proxy retries once, then returns 503 to caller

Sprint 3 (Session Expiration):
- Set JWT expiry to 1 minute for testing -> verify redirect after ~1 minute
- Login page shows "Your session has expired. Please log in again." when `?expired=true` in URL
- Normal 8-hour expiry works in production
- `setInterval(checkTokenExpiry, 60000)` runs on all protected pages

---

## 4. Observability (weight: 0.10)

| Score | Criteria |
|-------|----------|
| 0-2 | No logging added; Python Lambdas still silent |
| 3-4 | Basic print/logging statements added but not structured JSON |
| 5-6 | Structured JSON logging on all Python Lambdas with request_id and user_id |
| 7-8 | Structured logging + error entries include traceback + CloudWatch alarms configured |
| 9-10 | Full structured logging + CloudWatch dashboard + PITR on all 3 tables + error responses sanitized (no internal details leaked) |

**Test Scenarios:**

Sprint 4 (Structured Logging):
- Invoke any Python Lambda -> CloudWatch shows JSON log entry with `request_id`, `method`, `user_id`, `status_code`
- Trigger a validation error -> CloudWatch shows a WARN-level entry with field name and constraint
- Trigger a 500 error -> CloudWatch shows ERROR-level entry with full traceback and request context
- Logs do NOT contain passwords, API keys, or full request bodies with sensitive data

Sprint 4 (CloudWatch Alarms):
- 5xx Error Rate alarm exists (threshold > 5 in 5 minutes)
- Lambda Errors alarm exists (per function, threshold > 3 in 5 minutes)
- Lambda Throttles alarm exists (threshold > 0)
- DynamoDB Consumed RCU alarm exists (> 80% of provisioned)
- API Gateway 429s alarm exists (threshold > 10 in 5 minutes)

Sprint 4 (Operations):
- PITR shows "Enabled" on InventoryIQ, Users, and InventoryTransactions tables
- Error responses return `"Internal server error"` not Python tracebacks
- CloudWatch dashboard "InventoryIQ-Production" shows live metrics (request count, errors, latency, capacity)

---

## 5. Features (weight: 0.15)

| Score | Criteria |
|-------|----------|
| 0-2 | No new features implemented |
| 3-4 | Barcode scanning works on mobile but no external API lookup or bulk import |
| 5-6 | Barcode scanning + lookup + bulk CSV import with error reporting |
| 7-8 | Barcode + bulk import + demand forecasting with consumption rate and days-until-stockout |
| 9-10 | All features + forecast confidence levels + urgency dashboard + printable reorder list + forgot password flow |

**Test Scenarios:**

Sprint 5 (Barcode Scanning):
- Open add-item page on mobile -> tap Scan Barcode -> camera opens
- Scan a UPC barcode -> barcode number appears in form
- `GET /barcode/0049000006346` (Coca-Cola UPC) -> returns product name and description
- `GET /barcode/0000000000000` (invalid) -> returns 404
- Second call to same barcode -> served from DynamoDB cache (faster response)
- Scan in inventory page -> matching item highlighted or "not found" message
- Desktop without camera -> manual barcode entry field works
- Barcode stored with item and searchable in inventory table
- Items without barcode -> field shows "N/A" (not error)

Sprint 6 (Bulk Import):
- Upload CSV with 10 valid rows -> all imported, transaction logged as "bulk_create"
- Upload CSV with 3 invalid rows -> 7 imported, 3 errors reported with row numbers
- Upload CSV with 501 rows -> rejected with "Maximum 500 items per import"
- Upload CSV with wrong headers -> rejected with "Required column 'name' missing"
- Upload empty CSV -> rejected with "No data rows found"
- Drag CSV file onto dropzone -> preview shows first 5 rows
- Click Import -> progress indicator -> success summary with count
- Downloadable template CSV available
- Export with date/category filters works

Sprint 7 (Demand Forecasting):
- Item with 30 stock_out transactions over 90 days -> meaningful forecast with "high" confidence
- Item with 2 stock_out transactions -> forecast with "low" confidence
- Item with 0 stock_out transactions -> "Insufficient data for forecast"
- `GET /forecast/all` -> items sorted by days-until-stockout (most urgent first)
- Forecast page shows urgency cards: <7 days (red), <14 days (yellow), <30 days (green)
- Click item in forecast table -> consumption trend chart displays
- Print reorder list -> clean printable format with all items below reorder point

---

## Composite Score Calculation

```
final_score = (security * 0.30) + (data_integrity * 0.25) + (resilience * 0.20) + (observability * 0.10) + (features * 0.15)
```

| Final Score | Rating |
|-------------|--------|
| 9.0 - 10.0 | Exceptional -- production-grade with advanced features |
| 7.0 - 8.9 | Strong -- secure and resilient, most features delivered |
| 5.0 - 6.9 | Adequate -- core hardening done, features partial |
| 3.0 - 4.9 | Partial -- some improvements but critical security or integrity gaps |
| 0.0 - 2.9 | Insufficient -- spec not meaningfully implemented |

---

## Sprint-by-Sprint Pass/Fail Gates

Each sprint has a pass/fail gate. A sprint fails if any gate item is unmet.

### Sprint 1: Deploy + Verify
- [ ] UpdateItem.py error paths return proper HTTP codes (not 500 TypeError)
- [ ] All per-user reads use GSI queries (not scans)
- [ ] Ownership checks block cross-user mutations with 403
- [ ] All existing user flows work unchanged

### Sprint 2: Security Hardening
- [ ] Forged sessionStorage grants no access (401 from Proxy.py)
- [ ] CORS locked to production domain (not `*`)
- [ ] Brute force blocked after 5 failures (429 response)
- [ ] Invalid input rejected with field-level 400 errors
- [ ] Weak passwords rejected at registration

### Sprint 3: Data Integrity
- [ ] All mutations are atomic (TransactWriteItems)
- [ ] Concurrent updates on same item produce 409 (not silent overwrite)
- [ ] Proxy handles special characters in query strings
- [ ] Proxy times out after 10 seconds on hung downstream
- [ ] Sessions expire after 8 hours with clean redirect

### Sprint 4: Observability
- [ ] Every Lambda invocation produces structured JSON log entry
- [ ] CloudWatch alarms fire on 5xx errors and Lambda failures
- [ ] PITR enabled on all three DynamoDB tables
- [ ] Error responses never leak internal details

### Sprint 5: Barcode Scanning
- [ ] Camera-based barcode scanning works on mobile browsers
- [ ] Scanned barcode auto-populates item details from external API
- [ ] Barcode field stored with items and searchable
- [ ] External API failures handled gracefully

### Sprint 6: Bulk Import
- [ ] CSV import processes valid files and reports errors per-row
- [ ] Import modal has drag-and-drop, preview, and progress indicator
- [ ] Downloadable CSV template available
- [ ] Bulk imports logged in transaction history

### Sprint 7: Demand Forecasting
- [ ] Daily consumption rates calculated from transaction history
- [ ] Days-until-stockout prediction displayed per item
- [ ] Reorder recommendations generated automatically
- [ ] Confidence levels reflect data quality
- [ ] Urgency overview highlights critical items

### Sprint 8: Polish + Launch
- [ ] Forgot password works end-to-end via email
- [ ] Security audit finds zero critical issues
- [ ] Production launch checklist fully green

---

## Files to Inspect

### Existing Files (modified)
| File | What to check |
|------|---------------|
| `lambda/UpdateItem.py` | Line 56 bug fixed (no variable shadowing) + atomic writes + optimistic locking + JWT userID from header |
| `lambda/DeleteItem.py` | Atomic writes (TransactWriteItems) + JWT userID from header |
| `lambda/AddItem.py` | Atomic writes + `version: 1` on new items + JWT userID from header + input validation |
| `lambda/Authentication.mjs` | JWT signing on login/register + rate limiting + password complexity + forgot-password handler |
| `lambda/Proxy.py` | JWT validation + `urllib.parse.urlencode()` + 10s timeout + retry + CORS from env var |
| `lambda/GetAllItems.py` | GSI query (not scan) + structured logging + error sanitization |
| `lambda/GetTransactions.py` | GSI query + structured logging |
| `lambda/LowItemInsight.py` | GSI query + structured logging |
| `lambda/GetCategories.py` | GSI query + structured logging |
| `lambda/DeleteCategory.py` | Structured logging + CORS from env var |
| `lambda/DailyAlert.py` | Structured logging (still uses scan -- intentional) |
| `frontend/api.js` | Authorization Bearer header on all requests + 409 handling + barcode/import/forecast functions |
| `frontend/login.html` | JWT storage + forgot-password UI + password complexity hint |
| `frontend/utils.js` | JWT expiry check + periodic check interval + forecast nav link |
| `frontend/inventory.html` | Import CSV button + enhanced export + version field in updates |
| `frontend/add-item.html` | Barcode scanner button + QuaggaJS integration + barcode field |
| `frontend/style.css` | Camera viewfinder modal styles |

### New Files
| File | What to check |
|------|---------------|
| `lambda/BarcodeLookup.py` | External API calls (Open Food Facts + UPC Item DB) + DynamoDB caching + rate limiting |
| `lambda/BulkImport.py` | CSV parsing + row-level validation + batch_write_item in 25s + max 500 items + summary response |
| `lambda/DemandForecast.py` | Weighted moving average + confidence levels + days-until-stockout calculation |
| `lambda/ForecastAll.py` | Aggregates all item forecasts + sorts by urgency |
| `frontend/forecast.html` | Urgency cards + forecast table + consumption chart + printable reorder list |
| `frontend/import-template.csv` | Valid CSV template with headers and example rows |
