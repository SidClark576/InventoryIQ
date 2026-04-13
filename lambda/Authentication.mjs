import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
    DynamoDBDocumentClient,
    PutCommand,
    GetCommand,
    UpdateCommand,
    DeleteCommand
} from "@aws-sdk/lib-dynamodb";
import { SNSClient, SubscribeCommand, ListSubscriptionsByTopicCommand } from "@aws-sdk/client-sns";
import crypto from "crypto";

const client = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(client);
const snsClient = new SNSClient({});

const USERS_TABLE = process.env.USERS_TABLE || "Users";
const SNS_TOPIC_ARN = process.env.SNS_TOPIC_ARN;
const JWT_SECRET = process.env.JWT_SECRET;
const LOGIN_ATTEMPTS_TABLE = process.env.LOGIN_ATTEMPTS_TABLE || "LoginAttempts";
const CORS_ORIGIN = process.env.CORS_ORIGIN || "*";

const headers = {
    "Access-Control-Allow-Origin": CORS_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,x-api-key,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Content-Type": "application/json"
};

const hashPassword = (password, salt) => {
    return crypto.scryptSync(password, salt, 64).toString("hex");
};

// Validate password complexity: 8+ chars, uppercase, lowercase, digit
const validatePassword = (password) => {
    const minLength = password.length >= 8;
    const hasUppercase = /[A-Z]/.test(password);
    const hasLowercase = /[a-z]/.test(password);
    const hasDigit = /\d/.test(password);

    if (!minLength) return { valid: false, error: "Password must be at least 8 characters." };
    if (!hasUppercase) return { valid: false, error: "Password must contain at least one uppercase letter." };
    if (!hasLowercase) return { valid: false, error: "Password must contain at least one lowercase letter." };
    if (!hasDigit) return { valid: false, error: "Password must contain at least one digit." };

    return { valid: true };
};

// Sign JWT using HMAC-SHA256
const signJWT = (payload) => {
    const header = { alg: "HS256", typ: "JWT" };
    const headerB64 = Buffer.from(JSON.stringify(header)).toString("base64url");
    const payloadB64 = Buffer.from(JSON.stringify(payload)).toString("base64url");

    const signature = crypto
        .createHmac("sha256", JWT_SECRET)
        .update(`${headerB64}.${payloadB64}`)
        .digest("base64url");

    return `${headerB64}.${payloadB64}.${signature}`;
};

// Check rate limiting: return number of failed attempts in last 900 seconds
const checkRateLimit = async (email) => {
    const result = await docClient.send(new GetCommand({
        TableName: LOGIN_ATTEMPTS_TABLE,
        Key: { Email: email }
    }));

    const now = Math.floor(Date.now() / 1000);
    const attempts = result.Item?.attempts || [];

    // Filter to attempts in last 900 seconds (15 minutes)
    const recentAttempts = attempts.filter(ts => now - ts < 900);

    return recentAttempts.length;
};

// Record a failed login attempt
const recordFailedAttempt = async (email) => {
    const now = Math.floor(Date.now() / 1000);

    await docClient.send(new UpdateCommand({
        TableName: LOGIN_ATTEMPTS_TABLE,
        Key: { Email: email },
        UpdateExpression: "SET attempts = list_append(if_not_exists(attempts, :empty), :attempt), ttl = :ttl",
        ExpressionAttributeValues: {
            ":empty": [],
            ":attempt": [now],
            ":ttl": now + 900  // Auto-delete after 15 minutes
        }
    }));
};

// Clear failed login attempts on successful login
const clearFailedAttempts = async (email) => {
    await docClient.send(new DeleteCommand({
        TableName: LOGIN_ATTEMPTS_TABLE,
        Key: { Email: email }
    }));
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

            // Validate password complexity
            const passwordValidation = validatePassword(password);
            if (!passwordValidation.valid) {
                return {
                    statusCode: 400,
                    headers,
                    body: JSON.stringify({ message: passwordValidation.error })
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

            // Sign JWT: 8-hour expiry (28800 seconds)
            const now = Math.floor(Date.now() / 1000);
            const token = signJWT({
                sub: email,
                email: email,
                iat: now,
                exp: now + 28800
            });

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({
                    message: "User registered successfully! Please check your email to confirm your alert subscription.",
                    token: token,
                    email: email,
                    expiresIn: 28800
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

            // Check rate limiting BEFORE password validation (prevent enumeration)
            // Fail-open if LoginAttempts table doesn't exist yet
            let failedAttempts = 0;
            try {
                failedAttempts = await checkRateLimit(email);
            } catch (rateLimitErr) {
                console.warn("Rate limit check skipped:", rateLimitErr.message);
            }
            if (failedAttempts >= 5) {
                return {
                    statusCode: 429,
                    headers,
                    body: JSON.stringify({ message: "Too many login attempts. Please try again in 15 minutes." })
                };
            }

            const result = await docClient.send(new GetCommand({
                TableName: USERS_TABLE,
                Key: { Email: email }
            }));

            const user = result.Item;

            if (!user) {
                // Record failed attempt even for non-existent users (prevent enumeration)
                try { await recordFailedAttempt(email); } catch (e) { console.warn("recordFailedAttempt skipped:", e.message); }
                return {
                    statusCode: 401,
                    headers,
                    body: JSON.stringify({ message: "Invalid email or password." })
                };
            }

            const isValid = hashPassword(password, user.salt) === user.passwordHash;

            if (!isValid) {
                // Record failed attempt
                try { await recordFailedAttempt(email); } catch (e) { console.warn("recordFailedAttempt skipped:", e.message); }
                return {
                    statusCode: 401,
                    headers,
                    body: JSON.stringify({ message: "Invalid email or password." })
                };
            }

            // Clear failed attempts on successful login
            try { await clearFailedAttempts(email); } catch (e) { console.warn("clearFailedAttempts skipped:", e.message); }

            // Sign JWT: 8-hour expiry (28800 seconds)
            const now = Math.floor(Date.now() / 1000);
            const token = signJWT({
                sub: email,
                email: email,
                iat: now,
                exp: now + 28800
            });

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

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({
                    message: "Login successful!",
                    token: token,
                    email: user.Email,
                    expiresIn: 28800
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