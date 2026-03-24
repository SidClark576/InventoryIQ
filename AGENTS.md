# InventoryIQ — Codebase Reference

## Overview
InventoryIQ is a **serverless inventory management application** built on AWS. The frontend is a single-page app (SPA) hosted on **S3**, and the backend consists of **AWS Lambda** functions behind **API Gateway**, backed by **DynamoDB**, with **SNS** and **SQS** for stock alert notifications.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  S3 Static Website (Frontend)                               │
│  index.html  ·  api.js  ·  config.js                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS (API Gateway)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  API Gateway (REST, API-key auth)                           │
│  Base: https://xti5le6ccg.execute-api.us-east-1.amazonaws.com/prod │
│                                                             │
│  POST   /auth/register  →  index.mjs (Auth Lambda, Node)   │
│  POST   /auth/login     →  index.mjs                       │
│  GET    /items           →  GetAllItems.py                  │
│  POST   /items           →  AddItem.py                      │
│  PUT    /items/{itemID}  →  UpdateStock.py                  │
│  DELETE /items/{itemID}  →  DeleteItem.py                   │
│  GET    /insights        →  LowStockInsight.py              │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     DynamoDB       SNS Topic    SQS Queue
   InventoryIQ   (Alerts email) (Stock events)
   Users table
```

---

## File Inventory

### Frontend (deploy to S3)
| File | Purpose |
|---|---|
| `index.html` | SPA with Tailwind CSS (CDN), Inter font, glassmorphic "Indigo Nebula" design. Contains all page views (Auth, Dashboard, Inventory, Add/Edit Item, Insights) and client-side JS logic. |
| `api.js` | API wrapper functions: `authLogin`, `authRegister`, `getAllItems`, `addItem`, `updateItem`, `deleteItem`, `getInsights`. Includes try/catch fallbacks for endpoints that may return empty bodies. |
| `config.js` | Holds `CONFIG` object with `API_ENDPOINT`, `API_KEY`, and `AUTH_ENDPOINT`. |

### Backend (Lambda functions)
| File | Runtime | API Route | Description |
|---|---|---|---|
| `index.mjs` | Node.js (ESM) | `POST /auth/register`, `POST /auth/login` | User auth via DynamoDB `Users` table. Passwords hashed with `crypto.scryptSync`. Login returns a session token. |
| `AddItem.py` | Python | `POST /items` | Creates a new inventory item with a UUID. Writes to `InventoryIQ` DynamoDB table. |
| `GetAllItems.py` | Python | `GET /items` | Full table scan, returns all items with Decimal→float conversion. |
| `UpdateStock.py` | Python | `PUT /items/{itemID}` | Partial update (any subset of fields). Triggers SNS alerts on low/out-of-stock after update. |
| `DeleteItem.py` | Python | `DELETE /items/{itemID}` | Deletes item by `itemID` partition key. |
| `LowStockInsight.py` | Python | `GET /insights` | Scans all items, computes summary stats (total products, out-of-stock count, low stock count, inventory value, category breakdown), generates recommendations, publishes SNS alert and SQS message if stock issues exist. |

### Other files (not deployed)
| File | Purpose |
|---|---|
| `notes` | Reference file with ARNs and API keys. |
| `stitch_design.html` | Raw Stitch MCP-generated design reference (not used at runtime). |
| `update_css.py` | One-off utility script (not used at runtime). |

---

## DynamoDB Tables

### `InventoryIQ` (Inventory items)
- **Partition key:** `itemID` (String, UUID)
- **Attributes:** `name`, `description`, `category`, `quantity` (Number), `price` (Decimal), `lowStockThreshold` (Number), `createdAt`, `updatedAt`

### `Users` (Authentication)
- **Partition key:** `Email` (String)
- **Attributes:** `passwordHash`, `salt`, `createdAt`

---

## AWS Resources
| Resource | ARN / URL |
|---|---|
| API Gateway | `https://xti5le6ccg.execute-api.us-east-1.amazonaws.com/prod` |
| SNS Topic | `arn:aws:sns:us-east-1:753344699862:InventoryIQ-Alerts` |
| SQS Queue | `arn:aws:sqs:us-east-1:753344699862:InventoryIQ-StockQueue` |

---

## Frontend Design System
The UI uses the **"Indigo Nebula"** design system generated via Stitch MCP:
- **Framework:** Tailwind CSS (CDN), no build step required
- **Font:** Inter (Google Fonts CDN)
- **Theme:** Dark mode glassmorphism — deep indigo background (`#060e20`) with radial mesh gradients, translucent glass panels (`backdrop-filter: blur`), ghost borders
- **Primary color:** `#a3a6ff` (indigo), Secondary: `#c180ff` (purple), Tertiary: `#9bffce` (emerald)
- **Status badges:** Emerald = In Stock, Purple = Low Stock, Red = Out of Stock

---

## Key Conventions
1. **Auth flow:** Email/password. Passwords hashed with `scrypt` + random salt. Session token stored in `sessionStorage` (not a JWT — no server-side validation after login).
2. **API auth:** All inventory endpoints require `x-api-key` header. Auth endpoints do not.
3. **CORS:** All Lambdas return `Access-Control-Allow-Origin: *`.
4. **Error handling:** `api.js` wraps `updateItem` and `deleteItem` responses in try/catch to handle empty response bodies gracefully.
5. **No build step:** The frontend is plain HTML/JS loaded via CDN — just upload the 3 frontend files to S3.
