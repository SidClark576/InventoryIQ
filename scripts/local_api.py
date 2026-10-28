#!/usr/bin/env python3
"""Local API runner: serves the live API Gateway routes on localhost by calling the real Lambda handlers.

  /auth/*      -> lambda/Authentication.mjs (one `node` child per request)
  /proxy/*     -> lambda/Proxy.py, whose API_ENDPOINT points back at /_backend
  /_backend/*  -> the Python handler for each route frontend/src/api.ts calls (needs the seeded x-api-key)

Every AWS call goes to Floci (AWS_ENDPOINT_URL) with fake keys, and barcode lookups never reach the
internet. Started by scripts/dev_local.sh (`npm run dev:local`); see AGENTS.md "Local backend".
"""
import hmac
import importlib
import json
import os
import secrets
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAMBDA = ROOT / 'lambda'
PORT = int(os.environ.get('LOCAL_API_PORT', '3001'))
DEV_PORT = os.environ.get('LOCAL_DEV_PORT', '8000')
AWS_URL = os.environ.get('LOCAL_AWS_URL', 'http://localhost:4566')  # Floci container (scripts/dev_local.sh)
ACCOUNT = '000000000000'  # Floci's default account

# Fake AWS: everything points at Floci, so nothing can reach real AWS. Shared with local_seed.py.
AWS_ENV = {
    'AWS_ENDPOINT_URL': AWS_URL,
    'AWS_ACCESS_KEY_ID': 'local',
    'AWS_SECRET_ACCESS_KEY': 'local',
    'AWS_DEFAULT_REGION': 'us-east-1',
    'AWS_REGION': 'us-east-1',
    'API_KEY_SECRET': 'inventoryiq/api-key',
    'SES_SENDER': 'no-reply@panindo.local',
    'APP_URL': f'http://localhost:{DEV_PORT}',
    'SNS_TOPIC_ARN': f'arn:aws:sns:us-east-1:{ACCOUNT}:panindo-local-alerts',
    'SQS_QUEUE_URL': f'{AWS_URL}/{ACCOUNT}/panindo-local-stock',
    'IMPORT_BUCKET': 'inventoryiq-imports',
}
_NEVER = ('SENTRY_DSN', 'AWS_PROFILE', 'AWS_SESSION_TOKEN', 'AWS_SECURITY_TOKEN')

# (method, API Gateway resource, handler module): the routes frontend/src/api.ts calls.
ROUTES = [
    ('GET', '/items', 'GetAllItems'),
    ('POST', '/items', 'AddItem'),
    ('POST', '/items/import', 'BulkImport'),
    ('PUT', '/items/{itemID}', 'UpdateItem'),
    ('DELETE', '/items/{itemID}', 'DeleteItem'),
    ('POST', '/items/{itemID}/restore', 'RestoreItem'),
    ('GET', '/import/presign', 'BulkImport'),
    ('GET', '/import/{jobId}', 'BulkImport'),
    ('GET', '/insights', 'LowItemInsight'),
    ('GET', '/transactions', 'GetTransactions'),
    ('GET', '/categories', 'GetCategories'),
    ('DELETE', '/categories/{categoryName}', 'DeleteCategory'),
    ('GET', '/barcode/{code}', 'BarcodeLookup'),
    ('GET', '/orgs', 'Orgs'),
    ('POST', '/orgs/{id}/switch', 'Orgs'),
    ('PUT', '/orgs/{id}', 'Orgs'),
    ('GET', '/orgs/{id}/members', 'OrgMembers'),
    ('POST', '/orgs/{id}/invites', 'OrgInvites'),
    ('POST', '/org-invites/{token}/accept', 'OrgInvites'),
]

NODE_INVOKE = """
console.log = console.error;  // stdout carries only the handler result; logs go to the runner's stderr
const { handler } = await import(process.argv[1]);
let input = '';
for await (const chunk of process.stdin) input += chunk;
const context = { functionName: 'Authentication', awsRequestId: 'local', getRemainingTimeInMillis: () => 30000 };
process.stdout.write(JSON.stringify(await handler(JSON.parse(input), context)));
"""


def offline_lookup(_code):
    """Stands in for BarcodeLookup's internet lookups: unseeded codes are simply not found."""
    return None


def setup():
    """Point every SDK at Floci, then load the handlers that need patching. Call before handler()."""
    for name in _NEVER:
        os.environ.pop(name, None)
    os.environ.update(AWS_ENV)
    os.environ.update({
        'JWT_SECRET': secrets.token_hex(32),  # fresh per start; data resets on each start anyway
        'API_ENDPOINT': f'http://localhost:{PORT}/_backend',
        'LOG_STDOUT': '1',
    })
    if str(LAMBDA) not in sys.path:
        sys.path.insert(0, str(LAMBDA))
    import _logging
    dev = f'http://localhost:{DEV_PORT},http://127.0.0.1:{DEV_PORT}'
    os.environ['CORS_ORIGIN'] = f'{_logging.DEFAULT_CORS_ORIGINS},{dev}'  # read by Proxy and node at load
    barcode = importlib.import_module('BarcodeLookup')
    barcode._lookup_off = barcode._lookup_upc = offline_lookup


def handler(module):
    return importlib.import_module(module).lambda_handler


_api_key = ''


def api_key():
    """The seeded API key, read from Floci's Secrets Manager (what Proxy injects as x-api-key)."""
    global _api_key
    if not _api_key:
        try:
            import boto3
            _api_key = boto3.client('secretsmanager').get_secret_value(
                SecretId=AWS_ENV['API_KEY_SECRET'])['SecretString']
        except Exception:
            return ''
    return _api_key


def match_route(method, path):
    """Return (module, resource, decoded pathParameters or None) for a backend path, or None."""
    parts = path.strip('/').split('/')
    for route_method, resource, module in ROUTES:
        segs = resource.strip('/').split('/')
        if route_method != method or len(segs) != len(parts):
            continue
        params = {}
        for seg, part in zip(segs, parts):
            if seg.startswith('{'):
                params[seg[1:-1]] = urllib.parse.unquote(part)
            elif seg != part:
                break
        else:
            return module, resource, params or None
    return None


def _event(method, path, headers, body, query, resource, path_params):
    return {'httpMethod': method, 'path': path, 'resource': resource, 'headers': headers,
            'queryStringParameters': query, 'pathParameters': path_params, 'body': body}


def _json(status, body):
    return {'statusCode': status, 'headers': {'Content-Type': 'application/json'}, 'body': json.dumps(body)}


def invoke_auth(event):
    proc = subprocess.run(
        ['node', '--input-type=module', '-e', NODE_INVOKE, str(LAMBDA / 'Authentication.mjs')],
        input=json.dumps(event), stdout=subprocess.PIPE, text=True, timeout=30, check=False)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return _json(502, {'message': 'Authentication handler failed (see runner log)'})


def route(method, path, headers, body, query):
    """Dispatch one request the way API Gateway would. Returns a Lambda proxy response dict."""
    if path.startswith('/auth/'):
        return invoke_auth(_event(method, path, headers, body, query, '/auth/{proxy+}', None))
    if path.startswith('/proxy/'):
        rest = path[len('/proxy/'):]  # ponytail: kept URL-encoded so Proxy's urllib call survives spaces
        return handler('Proxy')(_event(method, path, headers, body, query, '/proxy/{proxy+}', {'proxy': rest}), None)
    if path.startswith('/_backend/'):
        key = api_key()
        if not key or not hmac.compare_digest(headers.get('x-api-key', ''), key):
            return _json(403, {'message': 'Forbidden'})
        sub = path[len('/_backend'):]
        hit = match_route(method, sub)
        if hit:
            module, resource, params = hit
            return handler(module)(_event(method, sub, headers, body, query, resource, params), None)
    return _json(404, {'message': 'Not Found'})


_seen_mail = set()
_mail_lock = threading.Lock()


def print_new_mail():
    """Print SES messages Floci captured since the last call (its /_aws/ses inspection route; nothing is sent)."""
    try:
        with urllib.request.urlopen(f'{AWS_URL}/_aws/ses', timeout=5) as r:
            messages = json.load(r).get('messages', [])
    except Exception:
        return
    with _mail_lock:
        for m in messages:
            if m.get('Id') in _seen_mail:
                continue
            _seen_mail.add(m.get('Id'))
            to = ', '.join((m.get('Destination') or {}).get('ToAddresses', []))
            body = m.get('Body') or {}
            print(f"\n[local email] to {to}: {m.get('Subject')}\n{body.get('text_part') or body.get('html_part')}\n",
                  flush=True)


class Handler(BaseHTTPRequestHandler):
    def _serve(self):
        url = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length).decode() if length else None
        headers = {k.lower(): v for k, v in self.headers.items()}
        query = dict(urllib.parse.parse_qsl(url.query)) or None
        res = route(self.command, url.path, headers, body, query)
        payload = (res.get('body') or '').encode()
        self.send_response(res.get('statusCode', 500))
        for k, v in (res.get('headers') or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        if self.command != 'OPTIONS' and not url.path.startswith('/_backend/'):
            print_new_mail()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _serve


def main():
    setup()
    print(f'Local API on http://localhost:{PORT} (Floci at {AWS_URL})', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
