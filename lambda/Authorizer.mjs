import crypto from "crypto";

const JWT_SECRET = process.env.JWT_SECRET || '';
if (!JWT_SECRET) {
    console.error('FATAL: JWT_SECRET environment variable is not set');
}

function _fromBase64url(str) {
    const pad = str + '='.repeat((4 - str.length % 4) % 4);
    return Buffer.from(pad.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
}

function _base64url(buf) {
    return buf.toString('base64').replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
}

/**
 * Verify HS256 JWT using Node.js crypto (no external deps).
 * Returns payload if valid, null otherwise.
 */
function _verifyJWT(token) {
    try {
        const parts = token.split('.');
        if (parts.length !== 3) return null;
        const [h, p, s] = parts;
        const expected = _base64url(
            crypto.createHmac('sha256', JWT_SECRET).update(`${h}.${p}`).digest()
        );
        const sBuf = _fromBase64url(s);
        const eBuf = _fromBase64url(expected);
        if (sBuf.length !== eBuf.length) return null;
        if (!crypto.timingSafeEqual(sBuf, eBuf)) return null;
        const payload = JSON.parse(_fromBase64url(p).toString());
        if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;
        return payload;
    } catch {
        return null;
    }
}

/**
 * API Gateway Custom Authorizer (TOKEN type).
 * Validates X-Session-Token as a signed JWT — no DynamoDB lookup needed.
 */
export const handler = async (event) => {
    const token = (
        event.headers?.['X-Session-Token'] ||
        event.headers?.['x-session-token'] ||
        ''
    ).trim();

    if (!token) {
        console.warn("Authorizer: Missing token in headers");
        throw new Error("Unauthorized");
    }

    const payload = _verifyJWT(token);
    if (!payload || !payload.sub) {
        console.warn("Authorizer: Invalid or expired JWT");
        throw new Error("Unauthorized");
    }

    return generatePolicy(payload.sub, 'Allow', event.methodArn, payload.sub);
};

const generatePolicy = (principalId, effect, resource, userID) => {
    const authResponse = { principalId };

    if (effect && resource) {
        authResponse.policyDocument = {
            Version: '2012-10-17',
            Statement: [{ Action: 'execute-api:Invoke', Effect: effect, Resource: resource }]
        };
    }

    authResponse.context = { userID };
    return authResponse;
};
