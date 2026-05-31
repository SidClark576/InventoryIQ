import json, boto3, urllib.request, urllib.parse, os, time, hmac, hashlib, base64
import _logging

FUNCTION_NAME = 'Proxy'

API_ENDPOINT     = os.environ['API_ENDPOINT']
API_KEY_SECRET   = os.environ.get('API_KEY_SECRET', 'inventoryiq/api-key')
# Fallback: read API_KEY directly from env (used if Secrets Manager not configured)
_API_KEY_ENV     = os.environ.get('API_KEY', '')
# CORS_ORIGIN: comma-separated list of allowed origins, or '*' for open
CORS_ORIGIN      = os.environ.get('CORS_ORIGIN', '*')
_CORS_ORIGINS    = {o.strip() for o in CORS_ORIGIN.split(',') if o.strip()} if CORS_ORIGIN != '*' else None
# JWT secret — must match Authentication Lambda
_JWT_SECRET      = os.environ.get('JWT_SECRET', '').encode()

secrets_client  = boto3.client('secretsmanager')

# API key cache: avoid Secrets Manager call on every request
_api_key_cache = {'value': _API_KEY_ENV, 'fetched_at': 0 if not _API_KEY_ENV else time.time()}
_API_KEY_TTL   = 300  # 5 minutes

_CORS_STATIC = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key,X-Session-Token,If-Match,Idempotency-Key',
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


def _verify_jwt(token: str):
    """
    Verify HS256 JWT using stdlib only — no DynamoDB, no external deps.
    Returns userID (sub claim) if valid, None otherwise.
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        def _pad(s: str) -> str:
            return s + '=' * ((4 - len(s) % 4) % 4)

        msg = f"{header_b64}.{payload_b64}".encode()
        sig = base64.urlsafe_b64decode(_pad(sig_b64))
        expected = hmac.new(_JWT_SECRET, msg, hashlib.sha256).digest()

        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(base64.urlsafe_b64decode(_pad(payload_b64)))
        if payload.get('exp', 0) <= time.time():
            return None

        return payload.get('sub')
    except Exception:
        return None


def lambda_handler(event, context):
    t0 = time.time()
    res = _handle(event, context)
    _logging.log_json(
        event=event,
        function=FUNCTION_NAME,
        latency_ms=(time.time() - t0) * 1000,
        status=res.get('statusCode'),
        is_error=res.get('statusCode', 200) >= 500,
    )
    return res


def _handle(event, context):
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
        _logging.log_json(event=event, function=FUNCTION_NAME,
                          level='WARN', count_request=False,
                          extra_metric=('iq.auth.invalid_session', 'Count'))
        return _unauthorized('Missing X-Session-Token header', origin)

    user_id = _verify_jwt(token)
    if not user_id:
        _logging.log_json(event=event, function=FUNCTION_NAME,
                          level='WARN', count_request=False,
                          extra_metric=('iq.auth.invalid_session', 'Count'))
        return _unauthorized('Invalid or expired session', origin)

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

    # Forward selected client headers downstream
    _PASSTHROUGH_HEADERS = ('if-match', 'idempotency-key')
    client_headers = event.get('headers') or {}
    for h in _PASSTHROUGH_HEADERS:
        val = client_headers.get(h) or client_headers.get(h.title())
        if val:
            fwd_headers[h] = val

    url = f"{API_ENDPOINT}{full_path}"

    # One retry on 5xx (transient backend errors); no retry on 4xx (client errors)
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                data=body.encode() if body else None,
                headers=fwd_headers,
                method=method
            )
            with urllib.request.urlopen(req, timeout=10) as res:
                status    = res.status
                resp_body = res.read().decode()
            if status >= 500 and attempt == 0:
                continue  # Retry once on 5xx
            return {'statusCode': status, 'headers': cors, 'body': resp_body}
        except urllib.error.HTTPError as e:
            err_code = e.code
            err_body = e.read().decode()
            if err_code >= 500 and attempt == 0:
                continue  # Retry once on 5xx
            return {'statusCode': err_code, 'headers': cors, 'body': err_body}
        except Exception as e:
            if attempt == 0:
                continue  # Retry once on network/timeout errors
            return {'statusCode': 500, 'headers': cors, 'body': json.dumps({'error': 'Internal Server Error'})}

    # Safety net — should not be reached
    return {'statusCode': 502, 'headers': cors, 'body': json.dumps({'error': 'Bad Gateway'})}
