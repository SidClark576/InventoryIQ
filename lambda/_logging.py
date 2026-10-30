import json
import time
import hashlib
import os
import re
import sys
import uuid
from datetime import date
from decimal import Decimal

# Add python_vendor to path for sentry-sdk
sys.path.append(os.path.join(os.path.dirname(__file__), 'python_vendor'))

_SECRET_HEADERS = {'x-session-token', 'authorization', 'cookie'}


def _scrub_event(event, hint):
    """Sentry before_send: AwsLambdaIntegration attaches request.url/headers; drop auth headers, redact invite tokens."""
    req = event.get('request') or {}
    if isinstance(req.get('headers'), dict):
        req['headers'] = {k: v for k, v in req['headers'].items() if k.lower() not in _SECRET_HEADERS}
    for key in ('url', 'query_string'):
        if isinstance(req.get(key), str):
            req[key] = redact_path(req[key])
    _scrub_breadcrumbs(event)
    return event


def _scrub_breadcrumbs(event):
    """httplib/stdlib breadcrumbs carry the request URL; redact invite tokens there too."""
    for crumb in (event.get('breadcrumbs') or {}).get('values') or []:
        data = crumb.get('data') or {}
        if isinstance(data.get('url'), str):
            data['url'] = redact_path(data['url'])
        if isinstance(crumb.get('message'), str):
            crumb['message'] = redact_path(crumb['message'])


try:
    import sentry_sdk  # type: ignore[import-not-found]  # vendored in python_vendor/ (see sys.path above)
    from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration  # type: ignore[import-not-found]
    _dsn = os.environ.get('SENTRY_DSN')
    if _dsn:
        sentry_sdk.init(
            dsn=_dsn,
            integrations=[AwsLambdaIntegration()],
            before_send=_scrub_event,
            before_send_transaction=_scrub_event,  # guard: tracing is off, scrub if re-enabled
        )
except ImportError:
    sentry_sdk = None

FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown')

# Structured stdout logs are on (PRD H5); LOG_STDOUT=0/false/no silences them.
# CloudWatch retention (30 days) is set per log group outside code.
_LOG_STDOUT = os.environ.get('LOG_STDOUT', '').lower() not in ('0', 'false', 'no')

_REQUEST_ID_RE = re.compile(r'[A-Za-z0-9-]{1,64}')
INTERNAL_ERROR = {'error': 'Internal Server Error', 'code': 'INTERNAL'}
_INVITE_TOKEN_RE = re.compile(r'(org-invites/)[^/?]+')


def redact_path(path):
    """Never log a raw invite token (AGENTS.md): org-invites/<token>/accept → org-invites/{token}/accept."""
    return _INVITE_TOKEN_RE.sub(r'\1{token}', path or '')


def _header(event, name):
    for key, value in ((event or {}).get('headers') or {}).items():
        if key.lower() == name:
            return (value or '').strip()
    return ''


def request_id(event):
    """Client X-Request-Id (<=64 chars of [A-Za-z0-9-]), else API Gateway's ID, else a new UUID."""
    rid = _header(event, 'x-request-id')
    if _REQUEST_ID_RE.fullmatch(rid):
        return rid
    return ((event or {}).get('requestContext') or {}).get('requestId') or str(uuid.uuid4())


def log_json(event=None, level='INFO', function=None, latency_ms=None,
             userID_hash=None, is_error=False, extra_metric=None,
             count_request=True, **kwargs):
    """
    Emit a structured log line without CloudWatch Embedded Metric Format (EMF)
    to save costs. Sentry integration can be added here later.
    """
    fn = function or FUNCTION_NAME

    record = {
        "level": level,
        "function": fn,
        "is_error": is_error,
    }

    if latency_ms is not None:
        record["latency_ms"] = round(latency_ms, 2)
    if extra_metric is not None:
        em_name = extra_metric[0]
        em_val  = extra_metric[2] if len(extra_metric) > 2 else 1
        record[em_name] = em_val
    if userID_hash is not None:
        record["userID_hash"] = userID_hash

    # Extract request context from event
    if event:
        record["httpMethod"] = event.get("httpMethod", "")
        path_params = event.get("pathParameters") or {}
        record["path"] = path_params.get("proxy", event.get("resource", ""))
        record["requestId"] = request_id(event)

    record.update(kwargs)
    if 'path' in record:
        record['path'] = redact_path(record['path'])
    if _LOG_STDOUT:
        print(json.dumps(record))


def capture_error(exc=None, event=None, **context):
    """Send an error to Sentry and log one ERROR line (type only, never the message).
    With `event`, tags requestId, userID_hash and orgID from it; extra context overrides.
    Sentry is a no-op if sentry_sdk is unavailable or SENTRY_DSN is unset."""
    if event is not None:
        context = {'requestId': request_id(event),
                   'userID_hash': hash_user(_header(event, 'x-iq-user')),
                   'orgID': _header(event, 'x-iq-org'), **context}
    context = {k: v for k, v in context.items() if v not in (None, '')}
    if 'path' in context:
        context['path'] = redact_path(context['path'])
    log_json(level='ERROR', is_error=True, error=type(exc).__name__ if exc else 'error', **context)
    if sentry_sdk is None:
        return
    with sentry_sdk.push_scope() as scope:
        for key, value in context.items():
            scope.set_tag(key, value)
        if exc is not None:
            sentry_sdk.capture_exception(exc)
        else:
            sentry_sdk.capture_message(context.get('message', 'error'), level='error')


def server_error(exc, event=None, headers=None):
    """Report `exc` with request context and return a generic 500 (never str(exc))."""
    capture_error(exc, event=event)
    return {'statusCode': 500, 'headers': headers or {}, 'body': json.dumps(INTERNAL_ERROR)}


# One shared list; Authentication.mjs repeats it (Node can't import this) and tests/unit/python/test_cors.py keeps them equal.
DEFAULT_CORS_ORIGINS = 'https://app.panindo.app,https://development.panindo-app.pages.dev,https://theinventoryiq.netlify.app,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,capacitor://localhost,https://localhost'
_CORS_ORIGIN = os.environ.get('CORS_ORIGIN', DEFAULT_CORS_ORIGINS)
_CORS_ORIGINS = (
    None if _CORS_ORIGIN == '*'
    else {o.strip() for o in _CORS_ORIGIN.split(',') if o.strip()}
)


def cors_headers(methods='OPTIONS,POST,GET,PUT,DELETE', extra_headers=None, request_origin=''):
    """CORS headers locked to the app origins + local Playwright unless CORS_ORIGIN=*."""
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Headers': 'Content-Type,x-api-key,X-Session-Token,If-Match,Idempotency-Key,X-IQ-Org',
        'Access-Control-Allow-Methods': methods,
    }
    if _CORS_ORIGINS is None:
        headers['Access-Control-Allow-Origin'] = '*'
    elif request_origin and request_origin in _CORS_ORIGINS:
        headers['Access-Control-Allow-Origin'] = request_origin
        headers['Vary'] = 'Origin'
    else:
        headers['Access-Control-Allow-Origin'] = 'https://app.panindo.app'
    if extra_headers:
        headers.update(extra_headers)
    return headers


def response(status_code, body, methods='OPTIONS,POST,GET,PUT,DELETE', extra_headers=None):
    """Standard JSON API response with CORS headers. Pass `methods` to override
    Access-Control-Allow-Methods; pass `extra_headers` to add response headers
    (e.g. ETag)."""
    return {
        'statusCode': status_code,
        'headers'   : cors_headers(methods, extra_headers),
        'body'      : json.dumps(body),
    }


def hash_user(user_id):
    """Return first 12 hex chars of sha256(user_id). Returns None if falsy."""
    if not user_id:
        return None
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def plain(row):
    """DynamoDB row -> JSON-ready dict: integral Decimals become int, others float (B4)."""
    return {k: (int(v) if v == v.to_integral_value() else float(v)) if isinstance(v, Decimal) else v
            for k, v in row.items()}


def json_body(event):
    """Parse the request body as a JSON object: (dict, None) or (None, 400 INVALID_JSON)."""
    try:
        body = json.loads((event or {}).get('body') or '{}')
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return None, response(400, {'error': 'Invalid JSON body', 'code': 'INVALID_JSON'})
    return body, None


def number_field(body, name, integer=False, default=None):
    """Non-negative number from `body[name]` (numeric strings accepted): (value, None) or (None, 400).
    Absent -> (default, None). Integers come back as int, other numbers as Decimal (A9)."""
    if name not in body:
        return default, None
    raw = body[name]
    try:
        num = Decimal(str(raw).strip())
        bad = (isinstance(raw, bool) or not num.is_finite() or num < 0 or num.adjusted() > 15  # SEC-1: int(1e10000000) pins the CPU
               or (integer and num != num.to_integral_value()))
    except ArithmeticError:  # decimal.InvalidOperation: not a number
        bad = True
    if bad:
        kind = 'integer' if integer else 'number'
        return None, response(400, {'error': f'{name} must be a non-negative {kind}',
                                    'code': 'INVALID_FIELD', 'field': name})
    return (int(num) if integer else num), None


def date_field(body, name):
    """`YYYY-MM-DD` date from `body[name]`: (value, None) or (None, 400).
    Absent -> (None, None); '' or null -> ('', None), which clears the field."""
    if name not in body:
        return None, None
    raw = body[name]
    if raw is None or raw == '':
        return '', None
    try:
        return date.fromisoformat(raw).isoformat(), None
    except (TypeError, ValueError):
        return None, response(400, {'error': f'{name} must be a date (YYYY-MM-DD)',
                                    'code': 'INVALID_FIELD', 'field': name})
