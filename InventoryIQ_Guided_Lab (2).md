# 🧪 Guided Lab: Building InventoryIQ on AWS

**Course:** IT 426 — Cloud Application Development  
**Lab Title:** Deploying a Serverless Inventory Management Application  
**Estimated Duration:** 90–120 minutes  
**Difficulty:** Intermediate  

---

## ⚠️ Important Lab Constraints

> - You are using **AWS Academy**. You do **not** have full AWS account access.
> - Use **LabRole** as the IAM role for **every** AWS service you configure.
> - Do **not** attempt to create new IAM roles or policies — use LabRole exclusively.
> - Your lab session has a time limit. Save your work frequently.
> - Resources are automatically deleted when your lab session ends.

---

## 🎯 Lab Objectives

By the end of this lab, you will be able to:

- Create and configure DynamoDB tables for a multi-user application
- Deploy Python and Node.js Lambda functions with environment variables
- Build a REST API with API Gateway using Lambda Proxy Integration
- Configure SNS topics and SQS queues for event-driven notifications
- Deploy a static frontend using AWS Amplify (manual deploy from S3)
- Test end-to-end functionality of a serverless application

---

## 🏗️ Architecture Overview

```
AWS Amplify (Frontend)
        │ HTTPS
        ▼
API Gateway (REST, x-api-key auth)
        │
  ┌─────┼──────────────────┐
  ▼     ▼                  ▼
DynamoDB  SNS Topic       SQS Queue
(3 tables) (Alerts)       (StockQueue)
```

---

## 📋 Prerequisites

Before starting, download the InventoryIQ source files from:  
**https://github.com/SidClark576/InventoryIQ**

You will need these files locally on your computer:
- `Authentication.mjs`
- `AddItem.py`, `GetAllItems.py`, `UpdateItem.py`, `DeleteItem.py`
- `LowItemInsight.py`, `GetTransactions.py`, `GetCategories.py`, `DeleteCategory.py`
- `DailyAlert.py`
- `login.html`, `dashboard.html`, `inventory.html`, `add-item.html`
- `insights.html`, `transactions.html`, `index.html`
- `api.js`, `config.js`, `utils.js`, `style.css`

---

## 🗂️ Task 1: Create DynamoDB Tables

You will create three DynamoDB tables that store inventory items, users, and transaction history.

---

### Task 1.1 — Create the `InventoryIQ` Table

1. In the AWS Management Console, use the search bar to navigate to **DynamoDB**.
2. In the left sidebar, click **Tables**.
3. Click the orange **Create table** button.
4. Configure the table:
   - **Table name:** `InventoryIQ`
   - **Partition key:** `itemID` — set type to **String**
   - Leave **Sort key** empty
5. Under **Table settings**, select **Customize settings**.
6. Under **Read/write capacity settings**, select **On-demand**.
7. Leave all other settings at their defaults.
8. Click **Create table**.

⏳ Wait for the table status to show **Active** before proceeding.

---

### Task 1.2 — Create the `Users` Table

1. Click **Create table** again.
2. Configure the table:
   - **Table name:** `Users`
   - **Partition key:** `Email` — set type to **String** *(capital E — case-sensitive)*
   - Leave **Sort key** empty
3. Under **Table settings**, select **Customize settings**.
4. Under **Read/write capacity settings**, select **On-demand**.
5. Click **Create table**.

⏳ Wait for **Active** status.

---

### Task 1.3 — Create the `InventoryTransactions` Table

1. Click **Create table** again.
2. Configure the table:
   - **Table name:** `InventoryTransactions`
   - **Partition key:** `transactionID` — set type to **String**
   - Leave **Sort key** empty
3. Under **Table settings**, select **Customize settings**.
4. Under **Read/write capacity settings**, select **On-demand**.
5. Click **Create table**.

⏳ Wait for **Active** status.

✅ **Checkpoint:** You should now have three tables listed: `InventoryIQ`, `Users`, and `InventoryTransactions`, all with **Active** status.

---

## 📣 Task 2: Create SNS Topic and SQS Queue

---

### Task 2.1 — Create the SNS Topic

1. Navigate to **Amazon SNS** using the search bar.
2. In the left sidebar, click **Topics**.
3. Click **Create topic**.
4. Configure the topic:
   - **Type:** Standard
   - **Name:** `InventoryIQ-Alerts`
5. Scroll down — leave all other settings at defaults.
6. Click **Create topic**.
7. **Copy the Topic ARN** from the topic details page — you will need this later.  
   It will look like: `arn:aws:sns:us-east-1:XXXXXXXXXXXX:InventoryIQ-Alerts`

> **Optional:** To receive email alerts, click **Create subscription**, set Protocol to **Email**, enter your email address, and confirm the subscription from your inbox.

---

### Task 2.2 — Create the SQS Queue

1. Navigate to **Amazon SQS** using the search bar.
2. Click **Create queue**.
3. Configure the queue:
   - **Type:** Standard
   - **Name:** `InventoryIQ-StockQueue`
4. Scroll down — leave all other settings at defaults.
5. Click **Create queue**.
6. **Copy the Queue URL** from the queue details page — you will need this later.  
   It will look like: `https://sqs.us-east-1.amazonaws.com/XXXXXXXXXXXX/InventoryIQ-StockQueue`

✅ **Checkpoint:** You have an SNS topic and SQS queue ready. Keep both ARN/URL values saved.

---

## ⚡ Task 3: Create Lambda Functions

You will create 10 Lambda functions. Each function is a standalone file. Follow the same base steps for each function, with differences noted per function.

---

### Base Steps for Every Lambda Function

> Repeat these steps for each function listed below. Specific settings are called out per function.

1. Navigate to **AWS Lambda** using the search bar.
2. Click **Create function**.
3. Select **Author from scratch**.
4. Set the **Function name** as listed in the table below.
5. Set the **Runtime** as listed below.
6. Under **Permissions**, expand **Change default execution role**.
7. Select **Use an existing role**.
8. In the dropdown, select **LabRole**. *(This is required — do not create a new role.)*
9. Click **Create function**.
10. On the function page, scroll to the **Code source** section.
11. Delete the existing placeholder code.
12. Paste the full contents of the corresponding source file.
13. Click **Deploy**.

---

### Lambda Functions to Create

| Function Name | Runtime | Source File |
|---|---|---|
| `Authentication` | Node.js 18.x (or latest) | `Authentication.mjs` |
| `AddItem` | Python 3.12 | `AddItem.py` |
| `GetAllItems` | Python 3.12 | `GetAllItems.py` |
| `UpdateItem` | Python 3.12 | `UpdateItem.py` |
| `DeleteItem` | Python 3.12 | `DeleteItem.py` |
| `LowItemInsight` | Python 3.12 | `LowItemInsight.py` |
| `GetTransactions` | Python 3.12 | `GetTransactions.py` |
| `GetCategories` | Python 3.12 | `GetCategories.py` |
| `DeleteCategory` | Python 3.12 | `DeleteCategory.py` |
| `DailyAlert` | Python 3.12 | `DailyAlert.py` |

---

### Task 3.1 — Set Environment Variables for Each Lambda

After deploying each function's code, you must set its environment variables.

1. On the Lambda function page, click the **Configuration** tab.
2. Click **Environment variables** in the left panel.
3. Click **Edit**, then **Add environment variable**.
4. Add the variables listed below for each function.
5. Click **Save**.

**Python inventory functions** (`AddItem`, `GetAllItems`, `UpdateItem`, `DeleteItem`, `GetCategories`, `DeleteCategory`):

| Key | Value |
|---|---|
| `DYNAMODB_TABLE` | `InventoryIQ` |
| `TRANSACTIONS_TABLE` | `InventoryTransactions` |

**`LowItemInsight` and `DailyAlert`** — add all four:

| Key | Value |
|---|---|
| `DYNAMODB_TABLE` | `InventoryIQ` |
| `TRANSACTIONS_TABLE` | `InventoryTransactions` |
| `SNS_TOPIC_ARN` | *(paste the SNS Topic ARN you copied in Task 2.1)* |
| `SQS_QUEUE_URL` | *(paste the SQS Queue URL you copied in Task 2.2)* |

**`GetTransactions`**:

| Key | Value |
|---|---|
| `DYNAMODB_TABLE` | `InventoryIQ` |
| `TRANSACTIONS_TABLE` | `InventoryTransactions` |

**`Authentication`** (Node.js):

| Key | Value |
|---|---|
| `USERS_TABLE` | `Users` |
| `SNS_TOPIC_ARN` | *(paste the SNS Topic ARN you copied in Task 2.1)* |

✅ **Checkpoint:** All 10 Lambda functions created, code deployed, and environment variables saved.

---

### Task 3.2 — Update `Authentication.mjs` to Subscribe Users on Registration

The default `Authentication.mjs` only writes new users to DynamoDB. You must update it so that every new user is automatically subscribed to the SNS topic — they will receive a confirmation email and future stock alerts.

#### Replace the full contents of the `Authentication` Lambda with this updated code:

```javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
    DynamoDBDocumentClient,
    PutCommand,
    GetCommand
} from "@aws-sdk/lib-dynamodb";
import { SNSClient, SubscribeCommand } from "@aws-sdk/client-sns";
import crypto from "crypto";

const client = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(client);
const snsClient = new SNSClient({});

const USERS_TABLE = process.env.USERS_TABLE || "Users";
const SNS_TOPIC_ARN = process.env.SNS_TOPIC_ARN;

const headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,x-api-key",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Content-Type": "application/json"
};

const hashPassword = (password, salt) => {
    return crypto.scryptSync(password, salt, 64).toString("hex");
};

export const handler = async (event) => {
    try {

        if (event.httpMethod === "OPTIONS") {
            return { statusCode: 200, headers, body: JSON.stringify({}) };
        }

        const body = event.body ? JSON.parse(event.body) : {};
        const path = event.path || event.rawPath || "";

        // ── REGISTER ──────────────────────────────────────────
        if (path.endsWith("/register")) {
            const { email, password } = body;

            if (!email || !password) {
                return {
                    statusCode: 400,
                    headers,
                    body: JSON.stringify({ message: "Email and password are required." })
                };
            }

            const salt = crypto.randomBytes(16).toString("hex");
            const hashedPassword = hashPassword(password, salt);

            // Write user to DynamoDB
            await docClient.send(new PutCommand({
                TableName: USERS_TABLE,
                ConditionExpression: "attribute_not_exists(Email)",
                Item: {
                    Email: email,
                    passwordHash: hashedPassword,
                    salt: salt,
                    createdAt: new Date().toISOString()
                }
            }));

            // Subscribe the new user's email to SNS topic for stock alerts
            if (SNS_TOPIC_ARN) {
                await snsClient.send(new SubscribeCommand({
                    TopicArn: SNS_TOPIC_ARN,
                    Protocol: "email",
                    Endpoint: email,
                    ReturnSubscriptionArn: true
                }));
            }

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({
                    message: "User registered successfully! Please check your email to confirm your alert subscription."
                })
            };
        }

        // ── LOGIN ─────────────────────────────────────────────
        if (path.endsWith("/login")) {
            const { email, password } = body;

            if (!email || !password) {
                return {
                    statusCode: 400,
                    headers,
                    body: JSON.stringify({ message: "Email and password are required." })
                };
            }

            const result = await docClient.send(new GetCommand({
                TableName: USERS_TABLE,
                Key: { Email: email }
            }));

            const user = result.Item;

            if (!user) {
                return {
                    statusCode: 401,
                    headers,
                    body: JSON.stringify({ message: "Invalid email or password." })
                };
            }

            const isValid = hashPassword(password, user.salt) === user.passwordHash;

            if (!isValid) {
                return {
                    statusCode: 401,
                    headers,
                    body: JSON.stringify({ message: "Invalid email or password." })
                };
            }

            const sessionToken = crypto.randomUUID();

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({
                    message: "Login successful!",
                    token: sessionToken,
                    email: user.Email
                })
            };
        }

        // ── NOT FOUND ─────────────────────────────────────────
        return {
            statusCode: 404,
            headers,
            body: JSON.stringify({ message: "Endpoint not found." })
        };

    } catch (error) {
        console.error("Auth Error:", error);

        if (error.name === "ConditionalCheckFailedException") {
            return {
                statusCode: 409,
                headers,
                body: JSON.stringify({ message: "An account with this email already exists." })
            };
        }

        return {
            statusCode: 500,
            headers,
            body: JSON.stringify({ message: "Internal Server Error", error: error.message })
        };
    }
};
```

1. In the AWS Lambda console, click the **Authentication** function.
2. In the **Code source** panel, delete all existing code.
3. Paste the full updated code above.
4. Click **Deploy**.

> **Note:** The `SNS_TOPIC_ARN` environment variable you added above is what connects this Lambda to your SNS topic. If it is missing, registration still works but no email is sent.

---

### What the User Experiences After Registration

| Step | What Happens |
|---|---|
| User fills in Register form and clicks **Register** | Lambda writes to DynamoDB, then calls `SNS Subscribe` |
| User receives email from `no-reply@sns.amazonaws.com` | Subject: *"AWS Notification — Subscription Confirmation"* |
| User clicks **"Confirm subscription"** in the email | Email is now an active SNS subscriber |
| Insights page visited or DailyAlert triggers | User receives stock alert emails automatically |

> ⚠️ **Subscription is pending until the user clicks the confirmation link.** AWS enforces this opt-in requirement — emails will not be delivered until confirmed. LabRole already has `sns:Subscribe` permission so no extra IAM policy is needed.

---

## 🔌 Task 4: Create the API Gateway

---

### Task 4.1 — Create the REST API

1. Navigate to **API Gateway** using the search bar.
2. Click **Create API**.
3. Under **REST API**, click **Build**.
4. Configure:
   - **API name:** `InventoryIQ-API`
   - **Description:** InventoryIQ REST API
   - **Endpoint type:** Regional
5. Click **Create API**.

---

### Task 4.2 — Create an API Key

1. In the left sidebar, click **API Keys**.
2. Click **Create API key**.
3. Set **Name:** `InventoryIQ-Key`
4. Select **Auto Generate**.
5. Click **Save**.
6. **Copy and save the API key value** — you will need it in `config.js` later.

---

### Task 4.3 — Create a Usage Plan

1. In the left sidebar, click **Usage Plans**.
2. Click **Create usage plan**.
3. Set **Name:** `InventoryIQ-Plan`
4. Under **Throttling**, you may leave defaults or uncheck to disable throttling.
5. Under **Quota**, uncheck **Enable quota** (avoids 429 errors during testing).
6. Click **Next**.
7. On the next screen, click **Add API stage** — you will come back to this after deploying a stage.

> ⚠️ You will link this usage plan to your API key and deployment stage in Task 4.8.

---

### Task 4.4 — Create Resources and Routes

You will now create the API resources and methods. The structure is:

```
/
├── /auth
│   ├── POST /auth/register
│   └── POST /auth/login
├── /items
│   ├── GET  /items
│   ├── POST /items
│   └── /{itemID}
│       ├── PUT    /items/{itemID}
│       └── DELETE /items/{itemID}
├── /insights
│   └── GET /insights
├── /transactions
│   └── GET /transactions
└── /categories
    ├── GET /categories
    └── /{categoryName}
        └── DELETE /categories/{categoryName}
```

#### Create `/auth` resource:
1. Select the root `/` resource.
2. Click **Create resource**.
3. Set **Resource name:** `auth`
4. Leave **Resource path** as `/auth`
5. ✅ Check **CORS** checkbox.
6. Click **Create resource**.

#### Create `/auth/register`:
1. Select the `/auth` resource.
2. Click **Create resource**, set name: `register`, check CORS → **Create resource**.
3. Select `/auth/register`, click **Create method**.
4. Set **Method type:** `POST`
5. Set **Integration type:** Lambda function
6. ✅ Enable **Lambda proxy integration**
7. Select your region, then select the `Authentication` Lambda function.
8. Click **Create method**.

#### Create `/auth/login`:
1. Select `/auth` resource.
2. Click **Create resource**, name: `login`, check CORS → **Create resource**.
3. Select `/auth/login`, click **Create method**.
4. Method type: `POST`, Lambda proxy integration ON, select `Authentication`.
5. Click **Create method**.

#### Create `/items` resource:
1. Select root `/`.
2. Click **Create resource**, name: `items`, check CORS → **Create resource**.

#### Create `GET /items`:
1. Select `/items`, click **Create method**.
2. Method type: `GET`, Lambda proxy integration ON, select `GetAllItems`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

#### Create `POST /items`:
1. Select `/items`, click **Create method**.
2. Method type: `POST`, Lambda proxy integration ON, select `AddItem`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

#### Create `/items/{itemID}` resource:
1. Select `/items` resource.
2. Click **Create resource**.
3. Set **Resource name:** `{itemID}` *(include the curly braces)*
4. Check CORS → **Create resource**.

#### Create `PUT /items/{itemID}`:
1. Select `/{itemID}`, click **Create method**.
2. Method type: `PUT`, Lambda proxy integration ON, select `UpdateItem`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

#### Create `DELETE /items/{itemID}`:
1. Select `/{itemID}`, click **Create method**.
2. Method type: `DELETE`, Lambda proxy integration ON, select `DeleteItem`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

#### Create `/insights` resource:
1. Select root `/`, create resource `insights`, check CORS → **Create resource**.
2. Select `/insights`, create method `GET`, Lambda proxy integration ON, select `LowItemInsight`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

#### Create `/transactions` resource:
1. Select root `/`, create resource `transactions`, check CORS → **Create resource**.
2. Select `/transactions`, create method `GET`, Lambda proxy integration ON, select `GetTransactions`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

#### Create `/categories` resource:
1. Select root `/`, create resource `categories`, check CORS → **Create resource**.
2. Select `/categories`, create method `GET`, Lambda proxy integration ON, select `GetCategories`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

#### Create `/categories/{categoryName}` resource:
1. Select `/categories`, create resource `{categoryName}` *(with curly braces)*, check CORS → **Create resource**.
2. Select `/{categoryName}`, create method `DELETE`, Lambda proxy integration ON, select `DeleteCategory`.
3. ✅ Set **API Key Required** to `true`.
4. Click **Create method**.

---

### Task 4.5 — Deploy the API

1. Click **Deploy API** (orange button, top right).
2. Under **Stage**, select **New stage**.
3. Set **Stage name:** `prod`
4. Click **Deploy**.
5. **Copy the Invoke URL** shown at the top of the stage screen.  
   It will look like: `https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod`

---

### Task 4.6 — Link API Key to Usage Plan

1. In the left sidebar, click **Usage Plans**.
2. Select `InventoryIQ-Plan`.
3. Click the **Associated API stages** tab → **Add API stage**.
4. Select `InventoryIQ-API` and stage `prod` → click the checkmark.
5. Click the **Associated API keys** tab → **Add API key to usage plan**.
6. Select `InventoryIQ-Key` → click the checkmark.
7. Click **Done**.

✅ **Checkpoint:** API deployed. You have your Invoke URL and API key saved.

---

## 🪣 Task 5: Prepare the S3 Bucket (Amplify Source)

---

### Task 5.1 — Create the S3 Bucket

1. Navigate to **Amazon S3** using the search bar.
2. Click **Create bucket**.
3. Set **Bucket name:** `inventoryiq-frontend-<your-initials>` *(must be globally unique)*
4. Set **AWS Region** to `us-east-1` (or your current region).
5. Under **Block Public Access settings**, leave all blocks **checked** (Amplify does not need public S3 access).
6. Click **Create bucket**.

---

### Task 5.2 — Update `config.js`

Before uploading, open `config.js` on your computer and update it with your actual API values:

```javascript
const CONFIG = {
  API_ENDPOINT: "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/prod",  // ← your Invoke URL
  API_KEY: "your-api-key-value-here"   // ← your API key from Task 4.2
};
```

Save the file.

---

### Task 5.3 — Upload Frontend Files to S3

1. Click your newly created bucket name.
2. Click **Upload**.
3. Click **Add files** and select all of these files from your local machine:
   - `login.html`
   - `dashboard.html`
   - `inventory.html`
   - `add-item.html`
   - `insights.html`
   - `transactions.html`
   - `index.html`
   - `api.js`
   - `config.js`
   - `utils.js`
   - `style.css`
4. Click **Upload**.

> ⚠️ Do **not** upload: `notes`, `stitch_design.html`, `CLAUDE.md`, `AGENTS.md`

✅ **Checkpoint:** 11 files uploaded to your S3 bucket.

---

## 🚀 Task 6: Deploy Frontend with AWS Amplify

---

### Task 6.1 — Create Amplify App

1. Navigate to **AWS Amplify** using the search bar.
2. Click **Deploy an app**.
3. Select **Deploy without Git** → click **Next**.
4. Configure the app:
   - **App name:** `Inventory IQ`
   - **Environment name:** `prod`
5. Under **Method**, select **Amazon S3**.
6. In **S3 location of objects to host**, click **Browse S3**.
7. Select the bucket you created in Task 5.1 (`inventoryiq-frontend-<your-initials>`).
8. Click **Save and deploy**.

⏳ Wait for the deployment status to show **Deployed** (green check).

---

### Task 6.2 — Note Your App URL

1. Once deployed, click on your app in the Amplify console.
2. Copy the **Domain** URL — it will look like:  
   `https://prod.xxxxxxxxxxxx.amplifyapp.com`

This is the public URL for your InventoryIQ application.

✅ **Checkpoint:** Your app is live on Amplify with a public URL.

---

## 🧪 Task 7: Test the Application End-to-End

---

### Task 7.1 — Register a New User

1. Open your Amplify app URL in a browser.
2. You should be redirected to the **Login** page.
3. Click the **Register** tab.
4. Enter a **real email address you can access** (e.g., your school email) and a password.
5. Click **Register**.
6. ✅ You should be automatically logged in and redirected to the Dashboard.
7. ✅ Check your email inbox — you should receive an **AWS Notification — Subscription Confirmation** email.
8. Click **"Confirm subscription"** in that email.
9. ✅ Your email is now subscribed to InventoryIQ stock alerts.

> ⚠️ Use a real email address you can access during the lab — the confirmation link must be clicked for alerts to work.

---

### Task 7.2 — Add an Inventory Item

1. In the sidebar, click **Inventory**.
2. Click **Add Item**.
3. Fill in the form:
   - **Name:** `Test Widget`
   - **Description:** `A test product`
   - **Category:** `General`
   - **Quantity:** `50`
   - **Price:** `9.99`
   - **Low Stock Threshold:** `10`
4. Click **Add Item**.
5. ✅ The item should appear in the Inventory table.

---

### Task 7.3 — Test Stock Adjustment

1. On the Inventory page, hover over the `Test Widget` row.
2. Click the **➖** (minus) button.
3. Enter `45` in the deduct amount field.
4. Click **Confirm**.
5. ✅ Quantity should drop to `5`. The badge should change to **Low Stock** (yellow).

---

### Task 7.4 — View Insights

1. In the sidebar, click **Insights**.
2. ✅ You should see a health score and the `Test Widget` listed as a low-stock item.
3. ✅ Confirm an SNS message was published (check your email if you set up a subscription).

---

### Task 7.5 — View Transactions

1. In the sidebar, click **Transactions**.
2. ✅ You should see at least two records: `create` (when item was added) and `stock_out` (when you deducted stock).
3. Use the **Type** filter dropdown — select `stock_out`.
4. ✅ Only the stock deduction transaction should appear.

---

### Task 7.6 — Test Category Management

1. Go to **Inventory**, click **Manage Categories**.
2. In the input field, type `Electronics` → click **Create**.
3. ✅ `Electronics` should appear as a new chip in the modal.
4. On an inventory row, change the category dropdown to `Electronics`.
5. ✅ A checkmark should briefly appear confirming the update.

---

### Task 7.7 — Test Delete and Logout

1. Hover over the `Test Widget` row → click the 🗑️ **Delete** button.
2. Confirm the deletion.
3. ✅ The item should be removed from the table.
4. Click the **Logout** button in the sidebar.
5. ✅ You should be redirected back to `login.html`.

---

## 🧹 Lab Cleanup

> ⚠️ If you are ending your lab session, AWS Academy will clean up resources automatically. If you want to manually clean up:

1. **DynamoDB** → Tables → Delete `InventoryIQ`, `Users`, `InventoryTransactions`
2. **Lambda** → Functions → Delete all 10 functions
3. **API Gateway** → APIs → Delete `InventoryIQ-API`
4. **SNS** → Topics → Delete `InventoryIQ-Alerts`
5. **SQS** → Queues → Delete `InventoryIQ-StockQueue`
6. **S3** → Empty bucket first, then delete bucket
7. **Amplify** → Apps → Delete `Inventory IQ`

---

## ❓ Review Questions

Answer these questions to check your understanding:

1. Why do all Lambda functions use **LabRole** instead of creating a custom IAM role?

2. What does **Lambda Proxy Integration** do, and what happens if it is not enabled?

3. Why is the `name` field in `UpdateItem.py` referenced as `#nm` instead of `name`?

4. What is the difference between how **SNS** and **SQS** are used in this application?

5. Why does `sessionStorage` clear when the browser is closed? How does this affect security compared to `localStorage`?

6. When a user registers, their email is subscribed to SNS but they receive a **"Subscription Confirmation"** email instead of a welcome email. Why does AWS require this confirmation step, and what happens if they never click it?

7. A user creates a new category called "Furniture" but does not assign it to any item. They refresh the page. Is "Furniture" still available? Why or why not?

8. Your application is returning all zeros on the Dashboard and blank tables on Inventory. What is the most likely cause, and how do you fix it?

---

## 📎 Reference: Service Summary

| Service | Purpose in InventoryIQ |
|---|---|
| **AWS Amplify** | Hosts static frontend HTML/JS files |
| **Amazon S3** | Source bucket for Amplify deployment |
| **API Gateway** | Routes HTTP requests to Lambda functions, enforces API key auth |
| **AWS Lambda** | Serverless backend logic (10 functions) |
| **Amazon DynamoDB** | NoSQL database (items, users, transactions) |
| **Amazon SNS** | Publishes stock alert notifications (email) |
| **Amazon SQS** | Queues stock events for async processing |
| **LabRole (IAM)** | Grants all Lambda functions permission to access AWS services |

---

*End of Guided Lab — InventoryIQ on AWS*  
*IT 426 · April 2026*

---

## 📎 Appendix: Complete Source Code

> Paste each block into the corresponding Lambda **Code source** editor and click **Deploy**.
> For `config.js`, `utils.js`, and `api.js`, save locally and upload to your S3 bucket.

---

### `Authentication.mjs` — Node.js 18.x

**Environment variables required:** `USERS_TABLE` = `Users` | `SNS_TOPIC_ARN` = *(your SNS Topic ARN)*

```javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
    DynamoDBDocumentClient,
    PutCommand,
    GetCommand
} from "@aws-sdk/lib-dynamodb";
import { SNSClient, SubscribeCommand } from "@aws-sdk/client-sns";
import crypto from "crypto";

const client = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(client);
const snsClient = new SNSClient({});

const USERS_TABLE = process.env.USERS_TABLE || "Users";
const SNS_TOPIC_ARN = process.env.SNS_TOPIC_ARN;

const headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,x-api-key",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Content-Type": "application/json"
};

const hashPassword = (password, salt) => {
    return crypto.scryptSync(password, salt, 64).toString("hex");
};

export const handler = async (event) => {
    try {
        if (event.httpMethod === "OPTIONS") {
            return { statusCode: 200, headers, body: JSON.stringify({}) };
        }

        const body = event.body ? JSON.parse(event.body) : {};
        const path = event.path || event.rawPath || "";

        // REGISTER
        if (path.endsWith("/register")) {
            const { email, password } = body;
            if (!email || !password) {
                return { statusCode: 400, headers, body: JSON.stringify({ message: "Email and password are required." }) };
            }
            const salt = crypto.randomBytes(16).toString("hex");
            const hashedPassword = hashPassword(password, salt);

            // Write user to DynamoDB
            await docClient.send(new PutCommand({
                TableName: USERS_TABLE,
                ConditionExpression: "attribute_not_exists(Email)",
                Item: {
                    Email: email,
                    passwordHash: hashedPassword,
                    salt: salt,
                    createdAt: new Date().toISOString()
                }
            }));

            // Subscribe user email to SNS topic for stock alerts
            if (SNS_TOPIC_ARN) {
                await snsClient.send(new SubscribeCommand({
                    TopicArn: SNS_TOPIC_ARN,
                    Protocol: "email",
                    Endpoint: email,
                    ReturnSubscriptionArn: true
                }));
            }

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ message: "User registered successfully! Please check your email to confirm your alert subscription." })
            };
        }

        // LOGIN
        if (path.endsWith("/login")) {
            const { email, password } = body;
            if (!email || !password) {
                return { statusCode: 400, headers, body: JSON.stringify({ message: "Email and password are required." }) };
            }
            const result = await docClient.send(new GetCommand({
                TableName: USERS_TABLE,
                Key: { Email: email }
            }));
            const user = result.Item;
            if (!user) {
                return { statusCode: 401, headers, body: JSON.stringify({ message: "Invalid email or password." }) };
            }
            const isValid = hashPassword(password, user.salt) === user.passwordHash;
            if (!isValid) {
                return { statusCode: 401, headers, body: JSON.stringify({ message: "Invalid email or password." }) };
            }
            const sessionToken = crypto.randomUUID();
            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ message: "Login successful!", token: sessionToken, email: user.Email })
            };
        }

        return { statusCode: 404, headers, body: JSON.stringify({ message: "Endpoint not found." }) };

    } catch (error) {
        console.error("Auth Error:", error);
        if (error.name === "ConditionalCheckFailedException") {
            return { statusCode: 409, headers, body: JSON.stringify({ message: "An account with this email already exists." }) };
        }
        return { statusCode: 500, headers, body: JSON.stringify({ message: "Internal Server Error", error: error.message }) };
    }
};
```

---

### `AddItem.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ` | `TRANSACTIONS_TABLE` = `InventoryTransactions`

```python
import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        if not body.get('name'):
            return response(400, {'error': 'Product name is required'})

        item_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        user_id = body.get('userID', '').strip()

        item = {
            'itemID': item_id,
            'userID': user_id,
            'name': body.get('name'),
            'description': body.get('description', ''),
            'category': body.get('category', 'Uncategorized'),
            'quantity': int(body.get('quantity', 0)),
            'price': Decimal(str(body.get('price', 0))),
            'lowStockThreshold': int(body.get('lowStockThreshold', 10)),
            'createdAt': timestamp,
            'updatedAt': timestamp
        }

        table.put_item(Item=item)
        item['price'] = float(item['price'])

        tx_table.put_item(Item={
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': item['name'],
            'userID': user_id,
            'changeType': 'create',
            'quantityBefore': 0,
            'quantityAfter': item['quantity'],
            'quantityDelta': item['quantity'],
            'notes': 'Item created',
            'createdAt': timestamp
        })

        return response(201, {'message': 'Item added successfully', 'item': item})
    except Exception as e:
        return response(500, {'error': str(e)})

def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body)
    }
```

---

### `GetAllItems.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ`

```python
import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

def lambda_handler(event, context):
    try:
        params = event.get('queryStringParameters') or {}
        user_id = params.get('userID', '').strip()

        if not user_id:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*',
                            'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'},
                'body': json.dumps({'items': [], 'count': 0})
            }

        result = table.scan(FilterExpression=Attr('userID').eq(user_id))
        items = result.get('Items', [])

        while 'LastEvaluatedKey' in result:
            result = table.scan(
                ExclusiveStartKey=result['LastEvaluatedKey'],
                FilterExpression=Attr('userID').eq(user_id)
            )
            items.extend(result.get('Items', []))

        items = [
            {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}
            for item in items
        ]

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'},
            'body': json.dumps({'items': items, 'count': len(items)})
        }
    except Exception as e:
        return {'statusCode': 500, 'headers': {'Access-Control-Allow-Origin': '*'}, 'body': json.dumps({'error': str(e)})}
```

---

### `UpdateItem.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ` | `TRANSACTIONS_TABLE` = `InventoryTransactions`

```python
import json
import uuid
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

def lambda_handler(event, context):
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        body = json.loads(event.get('body', '{}'))
        timestamp = datetime.utcnow().isoformat()
        existing = table.get_item(Key={'itemID': item_id}).get('Item', {})

        update_expr = 'SET updatedAt = :ts'
        expr_values = {':ts': timestamp}
        expr_names = {}

        if 'quantity' in body:
            update_expr += ', quantity = :qty'
            expr_values[':qty'] = int(body['quantity'])
        if 'name' in body:
            # 'name' is a reserved word in DynamoDB — use alias #nm
            update_expr += ', #nm = :name'
            expr_values[':name'] = body['name']
            expr_names['#nm'] = 'name'
        if 'price' in body:
            update_expr += ', price = :price'
            expr_values[':price'] = Decimal(str(body['price']))
        if 'category' in body:
            update_expr += ', category = :cat'
            expr_values[':cat'] = body['category']
        if 'description' in body:
            update_expr += ', description = :desc'
            expr_values[':desc'] = body['description']
        if 'lowStockThreshold' in body:
            update_expr += ', lowStockThreshold = :lst'
            expr_values[':lst'] = int(body['lowStockThreshold'])

        update_kwargs = {
            'Key': {'itemID': item_id},
            'UpdateExpression': update_expr,
            'ExpressionAttributeValues': expr_values,
            'ReturnValues': 'ALL_NEW'
        }
        if expr_names:
            update_kwargs['ExpressionAttributeNames'] = expr_names

        result = table.update_item(**update_kwargs)
        updated = result.get('Attributes', {})
        updated = {k: float(v) if isinstance(v, Decimal) else v for k, v in updated.items()}

        qty_before = int(existing.get('quantity', 0))
        qty_after = int(body['quantity']) if 'quantity' in body else qty_before

        if qty_after > qty_before:
            change_type = 'stock_in'
        elif qty_after < qty_before:
            change_type = 'stock_out'
        else:
            change_type = 'update'

        tx_table.put_item(Item={
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': body.get('name', existing.get('name', '')),
            'userID': body.get('userID', existing.get('userID', '')),
            'changeType': change_type,
            'quantityBefore': qty_before,
            'quantityAfter': qty_after,
            'quantityDelta': qty_after - qty_before,
            'notes': body.get('notes', ''),
            'createdAt': timestamp
        })

        return response(200, {'message': 'Item updated', 'item': updated})
    except Exception as e:
        return response(500, {'error': str(e)})

def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'},
        'body': json.dumps(body)
    }
```

---

### `DeleteItem.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ` | `TRANSACTIONS_TABLE` = `InventoryTransactions`

```python
import json
import uuid
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
tx_table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

def lambda_handler(event, context):
    try:
        item_id = event.get('pathParameters', {}).get('itemID')
        if not item_id:
            return response(400, {'error': 'itemID is required in path'})

        existing = table.get_item(Key={'itemID': item_id}).get('Item', {})
        table.delete_item(Key={'itemID': item_id})

        tx_table.put_item(Item={
            'transactionID': str(uuid.uuid4()),
            'itemID': item_id,
            'itemName': existing.get('name', ''),
            'userID': existing.get('userID', ''),
            'changeType': 'delete',
            'quantityBefore': int(existing.get('quantity', 0)),
            'quantityAfter': 0,
            'quantityDelta': -int(existing.get('quantity', 0)),
            'notes': 'Item deleted',
            'createdAt': datetime.utcnow().isoformat()
        })

        return response(200, {'message': f'Item {item_id} deleted successfully'})
    except Exception as e:
        return response(500, {'error': str(e)})

def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
                    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'},
        'body': json.dumps(body)
    }
```

---

### `GetCategories.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ`

```python
import json
import os
import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,GET'
}

def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    user_id = (event.get('queryStringParameters') or {}).get('userID', '')
    if not user_id:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID required'})}

    result = table.scan(FilterExpression=Attr('userID').eq(user_id))
    items = result.get('Items', [])

    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id)
        )
        items.extend(result.get('Items', []))

    categories = sorted(list(set(
        item.get('category', 'Uncategorized')
        for item in items
        if item.get('category')
    )))

    if 'Uncategorized' not in categories:
        categories.append('Uncategorized')
        categories.sort()

    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(categories)}
```

---

### `DeleteCategory.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ`

```python
import json
import os
import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
}

def lambda_handler(event, _context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    params = event.get('queryStringParameters') or {}
    user_id = params.get('userID', '')
    category_name = (event.get('pathParameters') or {}).get('categoryName', '')

    if not user_id or not category_name:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID and categoryName required'})}

    if category_name.lower() == 'uncategorized':
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Cannot delete Uncategorized'})}

    result = table.scan(
        FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
    )
    items = result.get('Items', [])

    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
        )
        items.extend(result.get('Items', []))

    items_updated = 0
    for item in items:
        table.update_item(
            Key={'itemID': item['itemID']},
            UpdateExpression='SET category = :cat',
            ExpressionAttributeValues={':cat': 'Uncategorized'}
        )
        items_updated += 1

    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps({'itemsUpdated': items_updated})}
```

---

### `GetTransactions.py` — Python 3.12

**Environment variables required:** `TRANSACTIONS_TABLE` = `InventoryTransactions`

```python
import json
import os
import boto3
from boto3.dynamodb.conditions import Attr
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,GET'
}

def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    user_id = (event.get('queryStringParameters') or {}).get('userID', '')
    if not user_id:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID required'})}

    result = table.scan(FilterExpression=Attr('userID').eq(user_id))
    items = result.get('Items', [])

    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id)
        )
        items.extend(result.get('Items', []))

    for item in items:
        for k, v in item.items():
            if isinstance(v, Decimal):
                item[k] = float(v)

    items.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(items[:200])}
```

---

### `LowItemInsight.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ` | `SNS_TOPIC_ARN` | `SQS_QUEUE_URL`

> This file is large. Copy it directly from the repository:
> **[LowItemInsight.py on GitHub](https://github.com/SidClark576/InventoryIQ/blob/main/LowItemInsight.py)**

Key behaviors:
- Scans all items for the given `userID`
- Classifies items as `out_of_stock` (qty = 0) or `low_stock` (qty ≤ threshold)
- Calculates health score: starts at 100, -25 per out-of-stock, -10 per low-stock
- Publishes SNS alert email if any items are at risk
- Queues a summary event to SQS for background processing
- Returns full insights JSON to the Insights dashboard

---

### `DailyAlert.py` — Python 3.12

**Environment variables required:** `DYNAMODB_TABLE` = `InventoryIQ` | `SNS_TOPIC_ARN`

> This file is large. Copy it directly from the repository:
> **[DailyAlert.py on GitHub](https://github.com/SidClark576/InventoryIQ/blob/main/DailyAlert.py)**

Key behaviors:
- Triggered by EventBridge scheduled rule (daily)
- Scans ALL items across ALL users (admin-level report)
- Builds a formatted plain-text email with ASCII health bar, out-of-stock list, and low-stock list
- Publishes email to SNS with a dynamic subject line based on severity
- Does NOT require an API Gateway endpoint

---

### `config.js` — Frontend Configuration

> ⚠️ **Replace all placeholder values** with your actual API Gateway Invoke URL and API Key before uploading to S3.

```javascript
const CONFIG = {
  API_ENDPOINT: "https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod",
  API_KEY: "YOUR-API-KEY-HERE",
  AUTH_ENDPOINT: "https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod/auth",
};
```

---

### `utils.js` — Shared Auth & Navigation Helpers

```javascript
function requireAuth() {
  if (!sessionStorage.getItem('userEmail')) window.location.href = 'login.html';
}

function initNav(activePageId) {
  const email = sessionStorage.getItem('userEmail') || '';
  const el = document.getElementById('nav-email');
  if (el) el.textContent = email;

  document.querySelectorAll('[data-page]').forEach(function(a) {
    const active = a.dataset.page === activePageId;
    a.classList.toggle('text-[#005ab4]', active);
    a.classList.toggle('bg-[#e8f0fe]', active);
    a.classList.toggle('border-[#005ab4]', active);
    a.classList.toggle('font-bold', active);
    a.classList.toggle('text-gray-500', !active);
    a.classList.toggle('border-transparent', !active);
    a.classList.toggle('font-medium', !active);
  });
}

function handleLogout() {
  sessionStorage.clear();
  window.location.href = 'login.html';
}
```

---

### `api.js` — API Fetch Wrappers

```javascript
// AUTH FUNCTIONS

function checkQuota(res) {
  if (res.status === 429) {
    throw new Error('API quota exceeded — please wait a moment and try again.');
  }
}

function getCurrentUserID() {
  return sessionStorage.getItem('userEmail') || '';
}

async function authRegister(email, password) {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  return { status: res.status, data: await res.json() };
}

async function authLogin(email, password) {
  const res = await fetch(`${CONFIG.AUTH_ENDPOINT}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  return { status: res.status, data: await res.json() };
}

// INVENTORY FUNCTIONS

async function getAllItems() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/items?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/items`;
  const res = await fetch(url, { headers: { "x-api-key": CONFIG.API_KEY } });
  checkQuota(res);
  const raw = await res.text();
  let data = [];
  if (raw) {
    try { data = JSON.parse(raw); } catch { data = []; }
  }
  if (!res.ok) {
    const errMsg = data && typeof data === 'object' ? data.error : null;
    throw new Error(errMsg || 'Failed to fetch items');
  }
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return [];
}

async function addItem(item) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-api-key": CONFIG.API_KEY },
    body: JSON.stringify(item)
  });
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to add item');
  return data;
}

async function updateItem(itemID, updates) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "x-api-key": CONFIG.API_KEY },
    body: JSON.stringify(updates)
  });
  checkQuota(res);
  let data;
  try { data = await res.json(); } catch { data = { message: 'Update failed' }; }
  if (!res.ok) throw new Error(data.error || data.message || 'Failed to update item');
  return data;
}

async function deleteItem(itemID) {
  const res = await fetch(`${CONFIG.API_ENDPOINT}/items/${itemID}?_cb=${Date.now()}`, {
    method: "DELETE",
    headers: { "x-api-key": CONFIG.API_KEY, "Content-Type": "application/json" },
    cache: "no-store",
    mode: "cors"
  });
  checkQuota(res);
  let data;
  try { data = await res.json(); } catch { data = { message: 'Delete failed' }; }
  if (!res.ok) throw new Error(data.error || data.message || 'Failed to delete item');
  return data;
}

async function getInsights() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/insights?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/insights`;
  const res = await fetch(url, { headers: { "x-api-key": CONFIG.API_KEY } });
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to fetch insights');
  return data;
}

async function getTransactions() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/transactions?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/transactions`;
  const res = await fetch(url, { headers: { "x-api-key": CONFIG.API_KEY } });
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to fetch transactions');
  return Array.isArray(data) ? data : [];
}

async function getCategories() {
  const userID = getCurrentUserID();
  const url = userID
    ? `${CONFIG.API_ENDPOINT}/categories?userID=${encodeURIComponent(userID)}`
    : `${CONFIG.API_ENDPOINT}/categories`;
  const res = await fetch(url, { headers: { "x-api-key": CONFIG.API_KEY } });
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to fetch categories');
  return Array.isArray(data) ? data : [];
}

async function deleteCategory(categoryName) {
  const userID = getCurrentUserID();
  const res = await fetch(
    `${CONFIG.API_ENDPOINT}/categories/${encodeURIComponent(categoryName)}?userID=${encodeURIComponent(userID)}`,
    { method: "DELETE", headers: { "x-api-key": CONFIG.API_KEY } }
  );
  checkQuota(res);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to delete category');
  return data;
}
```

---

*End of Guided Lab — InventoryIQ on AWS*  
*IT 426 · April 2026*
