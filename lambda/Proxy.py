import json, boto3, urllib.request, urllib.parse, os, time, hmac, hashlib, base64
from botocore.config import Config
import _logging
import _org
import _routes

FUNCTION_NAME = 'Proxy'

API_ENDPOINT     = os.environ.get('API_ENDPOINT', '')  # only the legacy http mode uses it
API_KEY_SECRET   = os.environ.get('API_KEY_SECRET', 'inventoryiq/api-key')
# Fallback: read API_KEY directly from env (used if Secrets Manager not configured)
_API_KEY_ENV     = os.environ.get('API_KEY', '')
# CORS_ORIGIN: comma-separated list of allowed origins, or '*' for open
CORS_ORIGIN      = os.environ.get('CORS_ORIGIN', _logging.DEFAULT_CORS_ORIGINS)
_CORS_ORIGINS    = {o.strip() for o in CORS_ORIGIN.split(',') if o.strip()} if CORS_ORIGIN != '*' else None
# invoke = call each route's Lambda directly (lambda:InvokeFunction); unset/http = legacy hop via API_ENDPOINT
PROXY_MODE       = os.environ.get('PROXY_MODE', '')


def _load_jwt_secret():
    """JWT secret (must match Authentication): SSM SecureString JWT_SECRET_PARAM, read once per cold start;
    the JWT_SECRET env var when the param is unset or the read fails."""
    param = os.environ.get('JWT_SECRET_PARAM')
    if param:
        try:
            return boto3.client('ssm').get_parameter(Name=param, WithDecryption=True)['Parameter']['Value']
        except Exception as e:
            _logging.capture_error(e, function=FUNCTION_NAME, path='ssm:JWT_SECRET_PARAM')
    return os.environ.get('JWT_SECRET', '')


_JWT_SECRET      = _load_jwt_secret().encode()

secrets_client  = boto3.client('secretsmanager')
# Proxy retries itself (_RETRY_METHODS), so the SDK must not: a retried write could apply twice.
lambda_client   = boto3.client('lambda', config=Config(retries={'max_attempts': 0}, read_timeout=10))

# API key cache: avoid Secrets Manager call on every request
_api_key_cache = {'value': _API_KEY_ENV, 'fetched_at': 0 if not _API_KEY_ENV else time.time()}
_API_KEY_TTL   = 300  # 5 minutes

_CORS_STATIC = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key,X-Session-Token,If-Match,Idempotency-Key,X-IQ-Org,X-Request-Id',
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE',
    'Access-Control-Expose-Headers': 'ETag,X-Request-Id',
}
# Only these are re-sent after a 5xx/timeout; a retried write could apply twice (PRD A3).
_RETRY_METHODS = ('GET', 'HEAD', 'OPTIONS')


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


def _forbidden(msg='Forbidden', origin=''):
    return {'statusCode': 403, 'headers': _cors_headers(origin), 'body': json.dumps({'error': msg})}


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
    rid = _logging.request_id(event)
    res = _handle(event, context, rid)
    res.setdefault('headers', {})['X-Request-Id'] = rid
    _logging.log_json(
        event=event,
        function=FUNCTION_NAME,
        latency_ms=(time.time() - t0) * 1000,
        status=res.get('statusCode'),
        is_error=res.get('statusCode', 200) >= 500,
        requestId=rid,
    )
    return res


def _handle(event, context, rid):
    method = event.get('httpMethod', 'GET')
    raw_headers = event.get('headers') or {}
    origin = raw_headers.get('origin') or raw_headers.get('Origin') or ''

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': _cors_headers(origin), 'body': ''}

    if not _JWT_SECRET:
        return _unauthorized('Server misconfigured', origin)

    # {proxy+} sends the sub-path in pathParameters
    path = event.get('pathParameters', {}).get('proxy', '')
    path = f"/{path}"  # e.g. /items, /insights, /auth/login

    # Auth endpoints bypass session validation — they create or destroy sessions
    send = _invoke if PROXY_MODE == 'invoke' else _forward
    if path.startswith('/auth/'):
        return send(event, path, method, user_id=None, origin=origin, rid=rid)

    # ── Session validation ──────────────────────────────────────
    # API Gateway lowercases header names; handle both cases defensively
    token = (
        raw_headers.get('x-session-token') or
        raw_headers.get('X-Session-Token') or
        ''
    ).strip()

    if not token:
        _logging.log_json(event=event, function=FUNCTION_NAME,
                          level='WARN', count_request=False, requestId=rid,
                          extra_metric=('iq.auth.invalid_session', 'Count'))
        return _unauthorized('Missing X-Session-Token header', origin)

    user_id = _verify_jwt(token)
    if not user_id:
        _logging.log_json(event=event, function=FUNCTION_NAME,
                          level='WARN', count_request=False, requestId=rid,
                          extra_metric=('iq.auth.invalid_session', 'Count'))
        return _unauthorized('Invalid or expired session', origin)

    # Org tenancy: if a workspace is selected (X-IQ-Org), the user must be an active member.
    # Org-management routes (GET /orgs, accept invite) send no X-IQ-Org and pass through.
    org_id = (raw_headers.get('x-iq-org') or raw_headers.get('X-IQ-Org') or '').strip()
    role = None
    if org_id:
        member = _org.get_membership(org_id, user_id)
        if not member:
            return _forbidden('Not a member of the selected organization', origin)
        role = member.get('role')

    return send(event, path, method, user_id=user_id, origin=origin, org_id=org_id, role=role, rid=rid)


def _trusted_headers(event, user_id, org_id, role):
    """Identity headers built fresh here, so any client-supplied x-iq-user / x-iq-org / x-iq-role are
    dropped (anti-spoofing), plus the client headers backends read (if-match, idempotency-key)."""
    out = {k: v for k, v in (('x-iq-user', user_id), ('x-iq-org', org_id), ('x-iq-role', role)) if v}
    client_headers = event.get('headers') or {}
    for h in ('if-match', 'idempotency-key'):
        val = client_headers.get(h) or client_headers.get(h.title())
        if val:
            out[h] = val
    return out


def _forward(event, path, method, user_id, origin='', org_id='', role=None, rid=''):
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
        'x-api-key': _get_api_key(),
        'x-request-id': rid,
        **_trusted_headers(event, user_id, org_id, role),
    }

    url = f"{API_ENDPOINT}{full_path}"

    # Safe methods get one retry on 5xx/network errors; writes and 4xx never retry
    last = 1 if method in _RETRY_METHODS else 0
    for attempt in range(last + 1):
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
                etag      = res.headers.get('ETag')
            if status >= 500 and attempt < last:
                continue
            return {'statusCode': status, 'headers': _with_etag(cors, etag), 'body': resp_body}
        except urllib.error.HTTPError as e:
            err_code = e.code
            err_body = e.read().decode()
            if err_code >= 500 and attempt < last:
                continue
            return {'statusCode': err_code, 'headers': _with_etag(cors, e.headers.get('ETag')), 'body': err_body}
        except Exception as e:
            if attempt < last:
                continue
            _logging.capture_error(e, requestId=rid, userID_hash=_logging.hash_user(user_id),
                                   orgID=org_id, path=path)
            return {'statusCode': 500, 'headers': cors, 'body': json.dumps({'error': 'Internal Server Error'})}

    # Safety net — should not be reached (every last attempt returns)
    return {'statusCode': 502, 'headers': cors, 'body': json.dumps({'error': 'Bad Gateway'})}


def _with_etag(headers, etag):
    """Pass the upstream ETag (item version) through; no other upstream header is forwarded."""
    return {**headers, 'ETag': etag} if etag else headers


def _invoke_lambda(name, event):
    """Invoke one backend Lambda synchronously; return its proxy response. Raises on FunctionError."""
    res = lambda_client.invoke(FunctionName=name, Payload=json.dumps(event))
    payload = json.loads(res['Payload'].read() or b'null')
    if res.get('FunctionError') or not isinstance(payload, dict) or 'statusCode' not in payload:
        raise RuntimeError(f"{name} failed: {res.get('FunctionError') or 'malformed response'}")
    return payload


def _invoke(event, path, method, user_id, origin='', org_id='', role=None, rid=''):
    """PROXY_MODE=invoke: call the route's Lambda with the event API Gateway would build (no x-api-key hop)."""
    cors = _cors_headers(origin)
    hit = _routes.match_route(method, path, _routes.ROUTES)
    if not hit:
        return {'statusCode': 404, 'headers': cors, 'body': json.dumps({'message': 'Not Found'})}
    name, resource, params = hit
    lambda_event = {
        'httpMethod': method, 'path': path, 'resource': resource,
        'headers': {'content-type': 'application/json', 'x-request-id': rid,
                    **_trusted_headers(event, user_id, org_id, role)},
        'queryStringParameters': event.get('queryStringParameters'),
        'pathParameters': params, 'body': event.get('body'),
    }
    # Safe methods get one retry on an invoke error/timeout; writes never retry (as in _forward)
    last = 1 if method in _RETRY_METHODS else 0
    for attempt in range(last + 1):
        try:
            res = _invoke_lambda(name, lambda_event)
            etag = (res.get('headers') or {}).get('ETag')
            return {'statusCode': res['statusCode'], 'headers': _with_etag(cors, etag), 'body': res.get('body') or ''}
        except Exception as e:
            if attempt == last:
                _logging.capture_error(e, requestId=rid, userID_hash=_logging.hash_user(user_id),
                                       orgID=org_id, path=path)
    # API Gateway's answer to a failed Lambda integration
    return {'statusCode': 502, 'headers': cors, 'body': json.dumps({'message': 'Internal server error'})}
