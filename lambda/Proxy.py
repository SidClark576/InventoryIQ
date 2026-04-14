import json, boto3, urllib.request, urllib.parse, os, time

API_ENDPOINT    = os.environ['API_ENDPOINT']
API_KEY         = os.environ['API_KEY']
SESSIONS_TABLE  = os.environ.get('SESSIONS_TABLE', 'Sessions')

dynamodb       = boto3.resource('dynamodb')
sessions_table = dynamodb.Table(SESSIONS_TABLE)

# Module-level session cache: { token: (userID, expiresAt, cachedAt) }
# Avoids a DynamoDB GetItem on every request for warm Lambda containers
_session_cache = {}
_CACHE_TTL = 60  # seconds

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key,X-Session-Token',
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
}

def _unauthorized(msg='Unauthorized'):
    return {'statusCode': 401, 'headers': CORS, 'body': json.dumps({'error': msg})}


def _validate_session(token):
    """
    Returns (userID, expiresAt) if token is valid and not expired.
    Returns (None, None) otherwise.
    Uses module-level cache with 60s TTL to reduce DynamoDB reads.
    """
    now = time.time()

    # Check warm cache first
    cached = _session_cache.get(token)
    if cached:
        user_id, expires_at, cached_at = cached
        if now - cached_at < _CACHE_TTL and expires_at > now:
            return user_id, expires_at
        # Evict stale cache entry
        _session_cache.pop(token, None)

    # Cache miss: hit DynamoDB
    resp = sessions_table.get_item(Key={'sessionToken': token})
    item = resp.get('Item')

    if not item:
        return None, None

    expires_at = int(item.get('expiresAt', 0))
    if expires_at <= now:
        return None, None

    user_id = item.get('userID', '')
    _session_cache[token] = (user_id, expires_at, now)
    return user_id, expires_at


def _slide_expiry(token, expires_at):
    """
    Extends session TTL by 8 hours if less than 4 hours remain.
    Best-effort: errors are swallowed so validation never blocks on this.
    """
    now = time.time()
    hours_remaining = (expires_at - now) / 3600
    if hours_remaining >= 4:
        return
    new_expiry = int(now) + (8 * 3600)
    try:
        sessions_table.update_item(
            Key={'sessionToken': token},
            UpdateExpression='SET expiresAt = :e',
            ExpressionAttributeValues={':e': new_expiry}
        )
        # Update cache
        if token in _session_cache:
            uid, _, cached_at = _session_cache[token]
            _session_cache[token] = (uid, new_expiry, cached_at)
    except Exception:
        pass  # Non-blocking


def lambda_handler(event, context):
    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    # {proxy+} sends the sub-path in pathParameters
    path = event.get('pathParameters', {}).get('proxy', '')
    path = f"/{path}"  # e.g. /items, /insights, /auth/login

    # Auth endpoints bypass session validation — they create or destroy sessions
    if path.startswith('/auth/'):
        return _forward(event, path, method, user_id=None)

    # ── Session validation ──────────────────────────────────────
    raw_headers = event.get('headers') or {}
    # API Gateway lowercases header names; handle both cases defensively
    token = (
        raw_headers.get('x-session-token') or
        raw_headers.get('X-Session-Token') or
        ''
    ).strip()

    if not token:
        return _unauthorized('Missing X-Session-Token header')

    user_id, expires_at = _validate_session(token)
    if not user_id:
        return _unauthorized('Invalid or expired session')

    # Slide expiry in background (best-effort)
    _slide_expiry(token, expires_at)

    return _forward(event, path, method, user_id=user_id)


def _forward(event, path, method, user_id):
    """Forward the request to the real API Gateway stage."""
    body = event.get('body') or ''

    # Build query string with proper URL encoding
    qs = event.get('queryStringParameters') or {}
    if qs:
        query = '&'.join(
            f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in qs.items()
        )
        full_path = f"{path}?{query}"
    else:
        full_path = path

    # Build forwarded headers: inject x-api-key + optionally x-iq-user
    # Strip any client-supplied x-iq-user to prevent user spoofing
    fwd_headers = {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY
    }
    if user_id:
        fwd_headers['x-iq-user'] = user_id

    try:
        req = urllib.request.Request(
            f"{API_ENDPOINT}{full_path}",
            data=body.encode() if body else None,
            headers=fwd_headers,
            method=method
        )
        with urllib.request.urlopen(req, timeout=10) as res:
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
