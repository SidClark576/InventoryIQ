import json, boto3, urllib.request, urllib.parse, os, time

API_ENDPOINT     = os.environ['API_ENDPOINT']
SESSIONS_TABLE   = os.environ.get('SESSIONS_TABLE', 'Sessions')
API_KEY_SECRET   = os.environ.get('API_KEY_SECRET', 'inventoryiq/api-key')
# Fallback: read API_KEY directly from env (used if Secrets Manager not configured)
_API_KEY_ENV     = os.environ.get('API_KEY', '')
# CORS_ORIGIN: comma-separated list of allowed origins, or '*' for open
CORS_ORIGIN      = os.environ.get('CORS_ORIGIN', '*')
_CORS_ORIGINS    = {o.strip() for o in CORS_ORIGIN.split(',') if o.strip()} if CORS_ORIGIN != '*' else None

dynamodb        = boto3.resource('dynamodb')
sessions_table  = dynamodb.Table(SESSIONS_TABLE)
secrets_client  = boto3.client('secretsmanager')

# Module-level session cache: { token: (userID, expiresAt, cachedAt) }
_session_cache = {}
_CACHE_TTL = 60  # seconds

# API key cache: avoid Secrets Manager call on every request
_api_key_cache = {'value': _API_KEY_ENV, 'fetched_at': 0 if not _API_KEY_ENV else time.time()}
_API_KEY_TTL   = 300  # 5 minutes

_CORS_STATIC = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key,X-Session-Token',
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
}


def _cors_headers(request_origin=''):
    """Return CORS headers. Echo origin if it matches allow-list; use '*' for open config."""
    h = dict(_CORS_STATIC)
    if _CORS_ORIGINS is None:
        # Open config — allow all
        h['Access-Control-Allow-Origin'] = '*'
    elif request_origin and request_origin in _CORS_ORIGINS:
        h['Access-Control-Allow-Origin'] = request_origin
        h['Vary'] = 'Origin'
    # No ACAO header if origin not in allow-list
    return h


def _get_api_key():
    """Return API key from warm cache or Secrets Manager. Falls back to env var."""
    now = time.time()
    if now - _api_key_cache['fetched_at'] < _API_KEY_TTL and _api_key_cache['value']:
        return _api_key_cache['value']
    try:
        resp  = secrets_client.get_secret_value(SecretId=API_KEY_SECRET)
        value = resp.get('SecretString', '')
        # Secret may be stored as plain string or JSON {"api_key": "..."}
        try:
            parsed = json.loads(value)
            value  = parsed.get('api_key') or parsed.get('value') or value
        except (json.JSONDecodeError, AttributeError):
            pass
        _api_key_cache['value']      = value
        _api_key_cache['fetched_at'] = now
        return value
    except Exception:
        # Fall back to env var if Secrets Manager unavailable
        return _API_KEY_ENV


def _unauthorized(msg='Unauthorized', origin=''):
    return {'statusCode': 401, 'headers': _cors_headers(origin), 'body': json.dumps({'error': msg})}


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
    raw_headers = event.get('headers') or {}
    origin = raw_headers.get('origin') or raw_headers.get('Origin') or ''

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': _cors_headers(origin), 'body': ''}

    # {proxy+} sends the sub-path in pathParameters
    path = event.get('pathParameters', {}).get('proxy', '')
    path = f"/{path}"  # e.g. /items, /insights, /auth/login

    # Auth endpoints bypass session validation — they create or destroy sessions
    if path.startswith('/auth/'):
        return _forward(event, path, method, user_id=None, origin=origin)

    # ── Session validation ──────────────────────────────────────
    # API Gateway lowercases header names; handle both cases defensively
    token = (
        raw_headers.get('x-session-token') or
        raw_headers.get('X-Session-Token') or
        ''
    ).strip()

    if not token:
        return _unauthorized('Missing X-Session-Token header', origin)

    user_id, expires_at = _validate_session(token)
    if not user_id:
        return _unauthorized('Invalid or expired session', origin)

    # Slide expiry in background (best-effort)
    _slide_expiry(token, expires_at)

    return _forward(event, path, method, user_id=user_id, origin=origin)


def _forward(event, path, method, user_id, origin=''):
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
    cors = _cors_headers(origin)
    fwd_headers = {
        'Content-Type': 'application/json',
        'x-api-key': _get_api_key()
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
                'headers': cors,
                'body': res.read().decode()
            }
    except urllib.error.HTTPError as e:
        return {
            'statusCode': e.code,
            'headers': cors,
            'body': e.read().decode()
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': cors,
            'body': json.dumps({'error': str(e)})
        }
