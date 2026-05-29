import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
    DynamoDBDocumentClient,
    PutCommand,
    GetCommand,
    DeleteCommand,
    UpdateCommand,
    QueryCommand
} from "@aws-sdk/lib-dynamodb";
import { SNSClient, SubscribeCommand, ListSubscriptionsByTopicCommand } from "@aws-sdk/client-sns";
import { SESClient, SendEmailCommand } from "@aws-sdk/client-ses";
import crypto from "crypto";

// ── Inline EMF metric helper ──────────────────────────────────
// Prints a single CloudWatch Embedded Metric Format JSON line.
// CloudWatch auto-extracts Namespace/InventoryIQ metrics from the _aws envelope.
function emitAuthMetric(metricName, path, email) {
    const userHash = email
        ? crypto.createHash('sha256').update(email).digest('hex').slice(0, 12)
        : undefined;
    const record = {
        _aws: {
            Timestamp: Date.now(),
            CloudWatchMetrics: [{
                Namespace: "InventoryIQ",
                Dimensions: [["function"]],
                Metrics: [{ Name: metricName, Unit: "Count" }]
            }]
        },
        level: "INFO",
        function: "Authentication",
        [metricName]: 1,
        path,
        ...(userHash ? { userID_hash: userHash } : {})
    };
    console.log(JSON.stringify(record));
}

const client = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(client);
const snsClient = new SNSClient({});
const sesClient = new SESClient({});

const USERS_TABLE          = process.env.USERS_TABLE           || "Users";
const SESSIONS_TABLE       = process.env.SESSIONS_TABLE        || "Sessions";
const AUTH_ATTEMPTS_TABLE  = process.env.AUTH_ATTEMPTS_TABLE   || "AuthAttempts";
const PASSWORD_RESETS_TABLE = process.env.PASSWORD_RESETS_TABLE || "PasswordResets";
const SNS_TOPIC_ARN        = process.env.SNS_TOPIC_ARN;
const SES_SENDER           = process.env.SES_SENDER            || "";  // verified SES sender email
const APP_URL              = process.env.APP_URL               || "";  // e.g. https://your-app.s3-website...

// Lifetimes
const SESSION_TTL_SECONDS = 8 * 60 * 60;   // 8 h
const LOCKOUT_SECONDS     = 15 * 60;        // 15 min rate-limit window
const RESET_TTL_SECONDS   = 60 * 60;        // 1 h password-reset link
const MAX_FAILURES        = 5;              // max failed logins before 429

// Password must have lowercase, uppercase, digit, min 8 chars
const PASSWORD_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/;

const headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,x-api-key,X-Session-Token",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Content-Type": "application/json"
};

const hashPassword = (password, salt) => {
    return crypto.scryptSync(password, salt, 64).toString("hex");
};

// ── Rate-limit helpers ────────────────────────────────────────

async function _isRateLimited(email) {
    const key = email.toLowerCase();
    const resp = await docClient.send(new GetCommand({
        TableName: AUTH_ATTEMPTS_TABLE,
        Key: { email: key }
    }));
    const item = resp.Item;
    if (!item) return false;
    const nowEpoch = Math.floor(Date.now() / 1000);
    // If the TTL window already expired (DynamoDB cleanup lag), treat as clear
    if (item.ttl && item.ttl < nowEpoch) return false;
    return (item.failCount || 0) >= MAX_FAILURES;
}

async function _recordFailedAttempt(email) {
    const key = email.toLowerCase();
    const ttl = Math.floor(Date.now() / 1000) + LOCKOUT_SECONDS;
    await docClient.send(new UpdateCommand({
        TableName: AUTH_ATTEMPTS_TABLE,
        Key: { email: key },
        // Increment counter; set TTL only on first failure (if_not_exists)
        UpdateExpression: 'ADD failCount :one SET #ttl = if_not_exists(#ttl, :ttl)',
        ExpressionAttributeNames: { '#ttl': 'ttl' },
        ExpressionAttributeValues: { ':one': 1, ':ttl': ttl }
    }));
}

async function _clearAttempts(email) {
    await docClient.send(new DeleteCommand({
        TableName: AUTH_ATTEMPTS_TABLE,
        Key: { email: email.toLowerCase() }
    }));
}

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

            // Enforce password complexity: min 8 chars, uppercase, lowercase, digit
            if (!PASSWORD_REGEX.test(password)) {
                return {
                    statusCode: 400,
                    headers,
                    body: JSON.stringify({
                        message: "Password must be at least 8 characters and include uppercase, lowercase, and a number."
                    })
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

            // Rate limit: reject if >= 5 failures in last 15 min
            if (await _isRateLimited(email)) {
                emitAuthMetric("iq.auth.rate_limited", path, email);
                return {
                    statusCode: 429,
                    headers: { ...headers, 'Retry-After': String(LOCKOUT_SECONDS) },
                    body: JSON.stringify({ message: "Too many failed attempts. Please wait 15 minutes before trying again." })
                };
            }

            const result = await docClient.send(new GetCommand({
                TableName: USERS_TABLE,
                Key: { Email: email }
            }));

            const user = result.Item;

            if (!user) {
                await _recordFailedAttempt(email);
                emitAuthMetric("iq.auth.login_fail", path, email);
                return {
                    statusCode: 401,
                    headers,
                    body: JSON.stringify({ message: "Invalid email or password." })
                };
            }

            const isValid = hashPassword(password, user.salt) === user.passwordHash;

            if (!isValid) {
                await _recordFailedAttempt(email);
                emitAuthMetric("iq.auth.login_fail", path, email);
                return {
                    statusCode: 401,
                    headers,
                    body: JSON.stringify({ message: "Invalid email or password." })
                };
            }

            // Successful login: clear any prior failed attempts
            await _clearAttempts(email);

            const sessionToken = crypto.randomUUID();
            const nowEpoch = Math.floor(Date.now() / 1000);
            const expiresAt = nowEpoch + SESSION_TTL_SECONDS;

            // Write session row to Sessions table with TTL
            await docClient.send(new PutCommand({
                TableName: SESSIONS_TABLE,
                Item: {
                    sessionToken,
                    userID: email,
                    createdAt: new Date().toISOString(),
                    expiresAt,
                    userAgent: (event.headers && (event.headers['User-Agent'] || event.headers['user-agent'] || '')).slice(0, 200)
                }
            }));

            if (SNS_TOPIC_ARN) {
                let isAlreadySubscribed = false;
                let nextToken = undefined;

                do {
                    const listResult = await snsClient.send(new ListSubscriptionsByTopicCommand({
                        TopicArn: SNS_TOPIC_ARN,
                        NextToken: nextToken
                    }));

                    const match = listResult.Subscriptions.find(
                        sub => sub.Endpoint === email && sub.SubscriptionArn !== "PendingConfirmation"
                    );

                    if (match) {
                        isAlreadySubscribed = true;
                        break;
                    }

                    nextToken = listResult.NextToken;
                } while (nextToken);

                if (!isAlreadySubscribed) {
                    await snsClient.send(new SubscribeCommand({
                        TopicArn: SNS_TOPIC_ARN,
                        Protocol: "email",
                        Endpoint: email,
                        ReturnSubscriptionArn: true
                    }));
                }
            }

            emitAuthMetric("iq.auth.login_success", path, email);
            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({
                    message: "Login successful!",
                    token: sessionToken,
                    email: user.Email,
                    expiresAt
                })
            };
        }

        // ── LOGOUT ────────────────────────────────────────────
        if (path.endsWith("/logout")) {
            // Read token from header; idempotent — no 404 if already gone
            const reqHeaders = event.headers || {};
            const token = reqHeaders['X-Session-Token'] || reqHeaders['x-session-token'] || '';
            if (token) {
                await docClient.send(new DeleteCommand({
                    TableName: SESSIONS_TABLE,
                    Key: { sessionToken: token }
                }));
            }
            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ message: "Logged out." })
            };
        }

        // ── FORGOT PASSWORD ───────────────────────────────────
        if (path.endsWith("/forgot-password")) {
            const { email } = body;
            if (!email) {
                return { statusCode: 400, headers, body: JSON.stringify({ message: "Email required." }) };
            }

            // Check user exists — but always return 200 to prevent email enumeration
            const userResp = await docClient.send(new GetCommand({
                TableName: USERS_TABLE,
                Key: { Email: email }
            }));

            if (userResp.Item && SES_SENDER && APP_URL) {
                try {
                    const resetToken = crypto.randomUUID();
                    const nowEpoch = Math.floor(Date.now() / 1000);
                    await docClient.send(new PutCommand({
                        TableName: PASSWORD_RESETS_TABLE,
                        Item: {
                            resetToken,
                            userID: email,
                            createdAt: new Date().toISOString(),
                            expiresAt: nowEpoch + RESET_TTL_SECONDS
                        }
                    }));
                    const baseUrl = APP_URL.replace(/\/$/, '');
                    await sesClient.send(new SendEmailCommand({
                        Source: SES_SENDER,
                        Destination: { ToAddresses: [email] },
                        Message: {
                            Subject: { Data: 'InventoryIQ — Password Reset' },
                            Body: {
                                Text: {
                                    Data: [
                                        `You requested a password reset for your InventoryIQ account.`,
                                        ``,
                                        `Reset link (valid 1 hour):`,
                                        `${baseUrl}/reset-password.html?token=${resetToken}`,
                                        ``,
                                        `If you did not request this, ignore this email — your password has not changed.`
                                    ].join('\n')
                                }
                            }
                        }
                    }));
                } catch (e) {
                    console.error("forgot-password send failed:", e);
                    // swallow — always return 200 to prevent email enumeration
                }
            }

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ message: "If that email is registered, a reset link has been sent." })
            };
        }

        // ── RESET PASSWORD ────────────────────────────────────
        if (path.endsWith("/reset-password")) {
            const { token, newPassword } = body;
            if (!token || !newPassword) {
                return { statusCode: 400, headers, body: JSON.stringify({ message: "token and newPassword required." }) };
            }
            if (!PASSWORD_REGEX.test(newPassword)) {
                return {
                    statusCode: 400,
                    headers,
                    body: JSON.stringify({ message: "Password must be at least 8 characters and include uppercase, lowercase, and a number." })
                };
            }

            // Verify reset token
            const resetResp = await docClient.send(new GetCommand({
                TableName: PASSWORD_RESETS_TABLE,
                Key: { resetToken: token }
            }));
            const resetItem = resetResp.Item;
            if (!resetItem) {
                return { statusCode: 400, headers, body: JSON.stringify({ message: "Invalid or expired reset link." }) };
            }
            const nowEpoch = Math.floor(Date.now() / 1000);
            if (resetItem.expiresAt < nowEpoch) {
                return { statusCode: 400, headers, body: JSON.stringify({ message: "Reset link has expired. Please request a new one." }) };
            }

            const userEmail = resetItem.userID;

            // Update password
            const newSalt = crypto.randomBytes(16).toString("hex");
            const newHash = hashPassword(newPassword, newSalt);
            await docClient.send(new UpdateCommand({
                TableName: USERS_TABLE,
                Key: { Email: userEmail },
                UpdateExpression: 'SET passwordHash = :h, salt = :s, updatedAt = :u',
                ExpressionAttributeValues: {
                    ':h': newHash,
                    ':s': newSalt,
                    ':u': new Date().toISOString()
                }
            }));

            // Delete the used reset token
            await docClient.send(new DeleteCommand({
                TableName: PASSWORD_RESETS_TABLE,
                Key: { resetToken: token }
            }));

            // Invalidate all active sessions for this user (force re-login everywhere)
            let lastKey;
            do {
                const sessionsResp = await docClient.send(new QueryCommand({
                    TableName: SESSIONS_TABLE,
                    IndexName: 'userID-index',
                    KeyConditionExpression: 'userID = :uid',
                    ExpressionAttributeValues: { ':uid': userEmail },
                    ProjectionExpression: 'sessionToken',
                    ExclusiveStartKey: lastKey
                }));
                for (const s of (sessionsResp.Items || [])) {
                    await docClient.send(new DeleteCommand({
                        TableName: SESSIONS_TABLE,
                        Key: { sessionToken: s.sessionToken }
                    }));
                }
                lastKey = sessionsResp.LastEvaluatedKey;
            } while (lastKey);

            // Clear any rate-limit lockout for this email
            await _clearAttempts(userEmail);

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ message: "Password reset successfully. Please log in with your new password." })
            };
        }

        // ── NOT FOUND ─────────────────────────────────────────
        return {
            statusCode: 404,
            headers,
            body: JSON.stringify({ message: "Endpoint not found." })
        };

    } catch (error) {
        console.error("Auth Error:", { name: error.name, message: error.message });

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
            body: JSON.stringify({ message: "Internal Server Error" })
        };
    }
};