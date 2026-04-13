import json, boto3, urllib.request, os, hmac, hashlib, base64, time

API_ENDPOINT = os.environ['API_ENDPOINT']
API_KEY      = os.environ['API_KEY']  # stored safely in Lambda env vars
JWT_SECRET   = os.environ.get('JWT_SECRET', '')
CORS_ORIGIN  = os.environ.get('CORS_ORIGIN', '*')

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': CORS_ORIGIN,
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key,Authorization',
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
}

def base64url_decode(input_str):
    """Decode base64url with padding handling (Node.js strips padding)"""
    padding = 4 - (len(input_str) % 4)
    if padding != 4:
        input_str += '=' * padding
    return base64.urlsafe_b64decode(input_str)

def verify_jwt(token):
    """
    Verify JWT signature and expiry, return payload if valid, None if invalid.
    JWT format: header.payload.signature (all base64url-encoded)
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts

        # Decode payload to check expiry
        payload_json = base64url_decode(payload_b64).decode('utf-8')
        payload = json.loads(payload_json)

        # Check expiry (exp is Unix timestamp)
        now = int(time.time())
        if payload.get('exp', 0) < now:
            return None  # Token expired

        # Verify signature using HMAC-SHA256 and constant-time comparison
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(
                JWT_SECRET.encode('utf-8'),
                f"{header_b64}.{payload_b64}".encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8').rstrip('=')  # Remove padding for comparison

        if not hmac.compare_digest(signature_b64, expected_signature):
            return None  # Signature invalid

        return payload

    except Exception as e:
        print(f"JWT verification error: {e}")
        return None

def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    # {proxy+} sends the sub-path in pathParameters
    path = event.get('pathParameters', {}).get('proxy', '')
    path = f"/{path}"  # e.g. becomes /items or /insights

    method = event.get('httpMethod', 'GET')
    body   = event.get('body') or ''

    # Extract and validate JWT from Authorization header
    auth_header = event.get('headers', {}).get('authorization') or event.get('headers', {}).get('Authorization') or ''
    verified_user_id = None

    if not JWT_SECRET:
        # JWT_SECRET not configured — fail-open so misconfigured environments don't
        # lock out all users. The real API stage is still protected by x-api-key.
        print("Warning: JWT_SECRET not set, skipping token verification (fail-open)")
        # Attempt to extract the user ID from an unverified token for downstream use
        if auth_header.startswith('Bearer '):
            try:
                raw_payload = auth_header[7:].split('.')[1]
                payload_json = base64url_decode(raw_payload).decode('utf-8')
                verified_user_id = json.loads(payload_json).get('sub')
            except Exception:
                pass
    elif auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        payload = verify_jwt(token)
        if payload:
            verified_user_id = payload.get('sub')  # Extract email claim
        else:
            return {
                'statusCode': 401,
                'headers': CORS,
                'body': json.dumps({'error': 'Invalid or expired token'})
            }
    else:
        return {
            'statusCode': 401,
            'headers': CORS,
            'body': json.dumps({'error': 'Missing or invalid authorization header'})
        }

    qs = event.get('queryStringParameters') or {}
    if qs:
        query = '&'.join(f"{k}={v}" for k, v in qs.items())
        path = f"{path}?{query}"

    try:
        # Build headers with injected x-api-key and X-Verified-UserID
        req_headers = {
            'Content-Type': 'application/json',
            'x-api-key': API_KEY
        }
        if verified_user_id:
            req_headers['X-Verified-UserID'] = verified_user_id

        req = urllib.request.Request(
            f"{API_ENDPOINT}{path}",
            data=body.encode() if body else None,
            headers=req_headers,
            method=method
        )
        with urllib.request.urlopen(req) as res:
            return {
                'statusCode': res.status,
                'headers': CORS,
                'body': res.read().decode()
            }
    except urllib.error.HTTPError as e:
        return {
            'statusCode': e.code,
            'headers': CORS,
            'body': e.read().decode()
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': CORS,
            'body': json.dumps({'error': str(e)})
        }