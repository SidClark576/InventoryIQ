import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
    DynamoDBDocumentClient,
    PutCommand,
    GetCommand,
    DeleteCommand
} from "@aws-sdk/lib-dynamodb";
import { SNSClient, SubscribeCommand, ListSubscriptionsByTopicCommand } from "@aws-sdk/client-sns";
import crypto from "crypto";

const client = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(client);
const snsClient = new SNSClient({});

const USERS_TABLE = process.env.USERS_TABLE || "Users";
const SESSIONS_TABLE = process.env.SESSIONS_TABLE || "Sessions";
const SNS_TOPIC_ARN = process.env.SNS_TOPIC_ARN;

// Session lifetime: 8 hours in seconds
const SESSION_TTL_SECONDS = 8 * 60 * 60;

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