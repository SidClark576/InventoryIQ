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