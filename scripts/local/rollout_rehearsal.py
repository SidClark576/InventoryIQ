#!/usr/bin/env python3
"""Rehearse the org rollout on Floci. Run by scripts/local/rehearse_rollout.sh (see AGENTS.md "Local backend").

1. Mirror live into Floci: the 15 functions (placeholder code, live handler names) and InventoryIQ-API's routes,
   stage `prod`. scripts/local_api.py (LOCAL_API_GATEWAY=1) serves only what that stage has deployed.
2. Make the seeded store look like live before the migration: no orgID on the owner's items and transactions
   (org + member rows stay, so GET /orgs answers with an org once the route exists). Or --copy-from-live EMAIL:
   that live user's items and transactions replace the seed (read-only scan with your AWS_PROFILE; user-run only).
3. Run each rollout_orgs.py step with --apply against Floci and, after each, act like main's frontend
   (ensureOrgContext: GET /orgs, switch to the first org and send X-IQ-Org, else legacy), list items and edit one.
   Prints a table; exits 1 on 0 items, a failed edit or an unexpected count.
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import local_api  # noqa: E402
import local_seed  # noqa: E402
import migrate_orgs  # noqa: E402
import rollout_orgs  # noqa: E402

API = f'http://localhost:{local_api.PORT}'
ROLE = f'arn:aws:iam::{local_api.ACCOUNT}:role/inventoryiq-lambda'
# (method, resource, function, apiKeyRequired) on live InventoryIQ-API, read 2026-10-29. Dead /suppliers* skipped.
LIVE_ROUTES = [
    ('GET', '/items', 'GetAllItems', True),
    ('POST', '/items', 'AddItem', True),
    ('PUT', '/items/{itemID}', 'UpdateItem', True),
    ('DELETE', '/items/{itemID}', 'DeleteItem', True),
    ('POST', '/items/{itemID}/restore', 'RestoreItem', True),
    ('GET', '/categories', 'GetCategories', True),
    ('DELETE', '/categories/{categoryName}', 'DeleteCategory', True),
    ('GET', '/transactions', 'GetTransactions', True),
    ('GET', '/insights', 'LowItemInsight', True),
    ('GET', '/barcode/{code}', 'BarcodeLookup', False),
    ('ANY', '/proxy/{proxy+}', 'Proxy', False),
    ('ANY', '/auth/{proxy+}', 'Authentication', False),
]


def live_rows(email):
    """One live user's items and transactions. Read-only: scans only, with the user's own AWS profile."""
    import boto3
    db = boto3.Session(profile_name=os.environ.get('AWS_PROFILE') or 'inventoryiq',
                       region_name=os.environ.get('AWS_REGION', 'us-east-1')).resource('dynamodb')
    email = migrate_orgs.normalize_email(email)
    return {t: [r for r in migrate_orgs._scan(db.Table(t)) if migrate_orgs.normalize_email(r.get('userID')) == email]
            for t, _ in migrate_orgs.DATA_TABLES}


def _placeholder():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('placeholder.py', '# replaced by rollout_orgs.py --step deploy\n')
    return buf.getvalue()


def mirror(session):
    lam, gw = session.client('lambda'), session.client('apigateway')
    code = _placeholder()
    for name in rollout_orgs.LIVE_FUNCTIONS:
        node = name == 'Authentication'
        handler = 'lambda_function' if name in rollout_orgs.FIX_HANDLER else name
        lam.create_function(FunctionName=name, Runtime='nodejs20.x' if node else 'python3.12', Role=ROLE,
                            Handler=f"{handler}.{'handler' if node else 'lambda_handler'}", Code={'ZipFile': code},
                            Timeout=15, MemorySize=256)
    api = gw.create_rest_api(name=local_api.API_NAME)['id']
    paths = {r['path']: r for r in gw.get_resources(restApiId=api)['items']}
    prefix = lam.get_function_configuration(FunctionName='AddItem')['FunctionArn'].rsplit(':', 1)[0]
    with contextlib.redirect_stdout(io.StringIO()):
        for method, path, function, api_key in LIVE_ROUTES:
            rollout_orgs.add_route(gw, api, paths, method, path, f'{prefix}:{function}', True, api_key)
        for path in [p for p in paths if p != '/']:
            rollout_orgs.add_route(gw, api, paths, 'OPTIONS', path, None, True, False)
    gw.create_deployment(restApiId=api, stageName=rollout_orgs.STAGE)
    print(f'Mirrored {len(rollout_orgs.LIVE_FUNCTIONS)} functions and {len(LIVE_ROUTES)} routes (stage prod)')


def prepare(db, live):
    """The owner's items and transactions lose orgID, as live before the migration; live rows replace the seed."""
    for table, pk in migrate_orgs.DATA_TABLES:
        t = db.Table(table)
        for row in migrate_orgs._scan(t):
            if row.get('userID') != local_seed.OWNER:
                continue
            if live is None:
                t.update_item(Key={pk: row[pk]}, UpdateExpression='REMOVE orgID')
            else:
                t.delete_item(Key={pk: row[pk]})
        for row in (live or {}).get(table, []):
            row.pop('orgID', None)
            t.put_item(Item=dict(row, userID=local_seed.OWNER))


def call(method, path, headers=None, body=None):
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw or 'null')
    except ValueError:
        return status, None


def old_app(token):
    """Headers main's frontend sends after ensureOrgContext: X-IQ-Org only when GET /orgs and the switch work."""
    headers = {'X-Session-Token': token}
    status, data = call('GET', '/proxy/orgs', headers)
    orgs = data.get('orgs') if status == 200 and isinstance(data, dict) else None
    if orgs and call('POST', f"/proxy/orgs/{orgs[0]['orgID']}/switch", headers)[0] == 200:
        headers['X-IQ-Org'] = orgs[0]['orgID']
    return headers


class Report:
    def __init__(self):
        self.rows = []

    def check(self, step, what, got, want):
        self.rows.append((step, what, got, want, 'ok' if got == want else 'FAIL'))

    def look(self, step, token, mode, count):
        """Old-app load: org context, item list and one edit (PUT with If-Match). Returns headers and items."""
        headers = old_app(token)
        status, data = call('GET', '/proxy/items', headers)
        items = (data or {}).get('items') or [] if status == 200 else []
        self.check(step, 'mode', 'org' if 'X-IQ-Org' in headers else 'legacy', mode)
        self.check(step, 'items', len(items), count)
        edit = 'no item'
        if items:
            item = items[0]
            edit = call('PUT', f"/proxy/items/{item['itemID']}", {**headers, 'If-Match': str(item.get('version', 1))},
                        {'quantity': int(item.get('quantity', 0)) + 1})[0]
        self.check(step, 'edit', edit, 200)
        return headers, items

    def print(self):
        print(f"\n{'after step':<16} {'check':<9} {'got':>8} {'want':>8}  result")
        for step, what, got, want, result in self.rows:
            print(f'{step:<16} {what:<9} {str(got):>8} {str(want):>8}  {result}')
        failed = sum(r[4] == 'FAIL' for r in self.rows)
        print(f"\n{'FAILED: ' + str(failed) + ' checks' if failed else 'PASS: every check'}")
        return 1 if failed else 0


def step(name):
    """Run one rollout_orgs.py step with --apply against Floci; returns its output (also printed)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = rollout_orgs.main(['--endpoint', local_api.AWS_URL, '--apply', '--step', name])
    print(out.getvalue(), end='', flush=True)
    if code:
        raise SystemExit(f'rollout_orgs --step {name} exited {code}')
    return out.getvalue()


def rehearse(token, base):
    r = Report()
    headers, items = r.look('none', token, 'legacy', base)
    victim = items[-1]['itemID'] if items else 'none'
    r.check('none', 'delete', call('DELETE', f'/proxy/items/{victim}', headers)[0], 200)
    r.check('none', 'restore', call('POST', f'/proxy/items/{victim}/restore', headers)[0], 502)  # lambda_function
    step('deploy')
    headers = old_app(token)
    r.check('deploy', 'restore', call('POST', f'/proxy/items/{victim}/restore', headers)[0], 200)
    add = {'name': 'Rollout rehearsal add', 'category': 'Drinks', 'price': 10, 'quantity': 5, 'lowStockThreshold': 2}
    r.check('deploy', 'add', call('POST', '/proxy/items', headers, add)[0], 201)  # AddItem answers 201 Created
    r.look('deploy', token, 'legacy', base + 1)
    step('migrate-routes')
    r.look('migrate-routes', token, 'org', base + 1)
    stamped = re.findall(r'(\d+) items to stamp', step('remigrate'))
    r.check('remigrate', 'stamped', int(stamped[-1]) if stamped else None, 0)
    r.look('remigrate', token, 'org', base + 1)
    step('domain')
    r.look('domain', token, 'org', base + 1)
    return r.print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--copy-from-live', metavar='EMAIL', help="copy this live user's store (read-only)")
    args = ap.parse_args()
    live = live_rows(args.copy_from_live) if args.copy_from_live else None  # before env points at Floci
    for name in local_api._NEVER:
        os.environ.pop(name, None)
    os.environ.update(local_api.AWS_ENV)
    import boto3
    session = boto3.Session()
    mirror(session)
    prepare(session.resource('dynamodb'), live)
    base = len(local_seed.ITEMS) if live is None else sum(not r.get('deletedAt') for r in live['InventoryIQ'])
    if not base:
        raise SystemExit('No active items to rehearse with')
    password = json.loads(local_seed.LOGIN_FILE.read_text())['password']
    status, data = call('POST', '/auth/login', body={'email': local_seed.OWNER, 'password': password})
    if status != 200:
        raise SystemExit(f'owner login failed: {status}')
    return rehearse(data['token'], base)


if __name__ == '__main__':
    sys.exit(main())
