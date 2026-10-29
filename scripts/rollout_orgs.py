#!/usr/bin/env python3
"""Org rollout, one step per run. SAFE BY DEFAULT: a dry run prints every call and writes nothing.

  deploy          update the 15 live Lambdas, fix the RestoreItem/PurgeDeletedItems handlers, create
                  Orgs/OrgMembers/OrgInvites. Adds no route, so old frontends stay in legacy mode.
  migrate-routes  migrate_orgs --apply, add the /orgs* routes + invoke permissions, redeploy `prod`,
                  migrate_orgs --apply again (stamps rows written in between). Run in one sitting.
  remigrate       migrate_orgs --apply only.
  domain          app.panindo.app: update every Lambda's code (new CORS defaults), then merge CORS_ORIGIN, APP_URL
                  and SES_SENDER into the env of the functions in DOMAIN_ENV. Other env keys stay; no value is printed.

  .venv/bin/python scripts/rollout_orgs.py --step deploy --endpoint http://localhost:4567 --apply   # Floci
  ROLLOUT_LIVE=1 AWS_PROFILE=inventoryiq .venv/bin/python scripts/rollout_orgs.py --step deploy --apply  # live

Rehearse first: bash scripts/local/rehearse_rollout.sh. Live runs are the user's call.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
os.environ.pop('SENTRY_DSN', None)  # Sentry must never get a crash frame holding Lambda env values (_merge_env)
import local_api  # noqa: E402
import migrate_orgs  # noqa: E402

sys.path.insert(0, str(local_api.LAMBDA))
import _logging  # noqa: E402

STEPS = ('deploy', 'migrate-routes', 'remigrate', 'domain')
STAGE = 'prod'
LIVE_FUNCTIONS = (
    'Proxy', 'AddItem', 'GetAllItems', 'UpdateItem', 'DeleteItem', 'RestoreItem', 'GetCategories',
    'DeleteCategory', 'GetTransactions', 'LowItemInsight', 'BarcodeLookup', 'DailyAlert', 'CascadeDeleteUser',
    'PurgeDeletedItems', 'Authentication',
)
FIX_HANDLER = ('RestoreItem', 'PurgeDeletedItems')  # live: lambda_function.lambda_handler; zips hold <Name>.py
ORG_FUNCTIONS = ('Orgs', 'OrgMembers', 'OrgInvites')
ORG_ROUTES = [
    ('GET', '/orgs', 'Orgs'),
    ('POST', '/orgs/{id}/switch', 'Orgs'),
    ('PUT', '/orgs/{id}', 'Orgs'),
    ('GET', '/orgs/{id}/members', 'OrgMembers'),
    ('POST', '/orgs/{id}/invites', 'OrgInvites'),
    ('POST', '/org-invites/{token}/accept', 'OrgInvites'),
]
CORS_ORIGIN = _logging.DEFAULT_CORS_ORIGINS
APP_URL = 'https://app.panindo.app'
SES_SENDER = 'noreply@panindo.app'
DOMAIN_ENV = {
    'Proxy': {'CORS_ORIGIN': CORS_ORIGIN},
    'Authentication': {'CORS_ORIGIN': CORS_ORIGIN, 'APP_URL': APP_URL, 'SES_SENDER': SES_SENDER},
    'OrgInvites': {'APP_URL': APP_URL, 'SES_SENDER': SES_SENDER},
}


def pack():
    """Zip every Lambda into lambda/<Name>.zip (deploy_lambdas.sh's dry run packs; its aws commands are dropped)."""
    subprocess.run(['bash', str(SCRIPTS / 'deploy_lambdas.sh')], check=True, stdout=subprocess.DEVNULL)


def zip_bytes(name):
    return (local_api.LAMBDA / f'{name}.zip').read_bytes()


def _wait(lam, name, waiter='function_updated'):
    lam.get_waiter(waiter).wait(FunctionName=name)


def _update_code(lam, name, apply):
    print(f'  update code {name}')
    if apply:
        lam.update_function_code(FunctionName=name, ZipFile=zip_bytes(name))
        _wait(lam, name)


def _vars(conf):
    return (conf.get('Environment') or {}).get('Variables') or {}


def _exists(lam, name):
    try:
        lam.get_function_configuration(FunctionName=name)
        return True
    except lam.exceptions.ResourceNotFoundException:
        return False


def deploy(clients, apply):
    lam = clients['lambda']
    pack()
    for name in LIVE_FUNCTIONS:
        _update_code(lam, name, apply)
        want = f'{name}.lambda_handler'
        if name in FIX_HANDLER and lam.get_function_configuration(FunctionName=name)['Handler'] != want:
            print(f'  set handler {name} -> {want}')
            if apply:
                lam.update_function_configuration(FunctionName=name, Handler=want)
                _wait(lam, name)
    base = lam.get_function_configuration(FunctionName='AddItem')
    dsn = _vars(base).get('SENTRY_DSN')
    for name in ORG_FUNCTIONS:
        if _exists(lam, name):
            _update_code(lam, name, apply)
            continue
        print(f"  create function {name} (AddItem's runtime, role, timeout, memory{', SENTRY_DSN' if dsn else ''})")
        if apply:
            lam.create_function(
                FunctionName=name, Runtime=base['Runtime'], Role=base['Role'], Handler=f'{name}.lambda_handler',
                Code={'ZipFile': zip_bytes(name)}, Timeout=base['Timeout'], MemorySize=base['MemorySize'],
                Environment={'Variables': {'SENTRY_DSN': dsn} if dsn else {}})
            _wait(lam, name, 'function_active_v2')


def _resource(gw, api, paths, path, apply):
    if path in paths:
        return paths[path]['id']
    parent, part = path.rsplit('/', 1)
    parent_id = _resource(gw, api, paths, parent or '/', apply)
    print(f'  create resource {path}')
    rid = gw.create_resource(restApiId=api, parentId=parent_id, pathPart=part)['id'] if apply else None
    paths[path] = {'id': rid, 'path': path, 'resourceMethods': {}}
    return rid


def add_route(gw, api, paths, method, path, function_arn, apply, api_key=True):
    """Put `method path` on the REST API as AWS_PROXY to function_arn (None = MOCK), creating missing resources.
    paths = {path: get_resources item}, updated in place. A method already there is left alone."""
    rid = _resource(gw, api, paths, path, apply)
    methods = paths[path].setdefault('resourceMethods', {})
    if method in methods:
        print(f'  keep {method} {path} (already there)')
        return
    methods[method] = {}
    print(f"  add {method} {path} -> {function_arn.rsplit(':', 1)[-1] if function_arn else 'MOCK'}")
    if not apply:
        return
    gw.put_method(restApiId=api, resourceId=rid, httpMethod=method, authorizationType='NONE', apiKeyRequired=api_key)
    if function_arn:
        region = function_arn.split(':')[3]
        gw.put_integration(restApiId=api, resourceId=rid, httpMethod=method, type='AWS_PROXY',
                           integrationHttpMethod='POST',
                           uri=f'arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{function_arn}/invocations')
    else:
        gw.put_integration(restApiId=api, resourceId=rid, httpMethod=method, type='MOCK',
                           requestTemplates={'application/json': '{"statusCode": 200}'})


def rest_api(gw):
    api = next((a['id'] for a in gw.get_rest_apis(limit=500)['items'] if a['name'] == local_api.API_NAME), None)
    if not api:
        raise SystemExit(f'REST API {local_api.API_NAME} not found')
    return api


def migrate_routes(clients, apply):
    gw, lam = clients['apigateway'], clients['lambda']
    migrate_orgs.run(apply)
    api = rest_api(gw)
    paths = {r['path']: r for r in gw.get_resources(restApiId=api, embed=['methods'], limit=500)['items']}
    prefix = lam.get_function_configuration(FunctionName='AddItem')['FunctionArn'].rsplit(':', 1)[0]
    for method, path, name in ORG_ROUTES:
        add_route(gw, api, paths, method, path, f'{prefix}:{name}', apply)
    region, account = prefix.split(':')[3:5]
    for name in ORG_FUNCTIONS:
        print(f'  allow API Gateway to invoke {name}')
        if not apply:
            continue
        try:
            lam.add_permission(FunctionName=name, StatementId='inventoryiq-api', Action='lambda:InvokeFunction',
                               Principal='apigateway.amazonaws.com',
                               SourceArn=f'arn:aws:execute-api:{region}:{account}:{api}/*')
        except lam.exceptions.ResourceConflictException:
            print(f'    {name} already allowed')
    print(f'  deploy stage {STAGE}')
    if apply:
        gw.create_deployment(restApiId=api, stageName=STAGE)
    migrate_orgs.run(apply)


def remigrate(clients, apply):
    migrate_orgs.run(apply)


def _merge_env(lam, name, updates, apply):
    """Overlay `updates` on the function's env; every other key stays. Prints key names only, never values."""
    variables = {**_vars(lam.get_function_configuration(FunctionName=name)), **updates}
    print(f"  set env {name}: {', '.join(sorted(updates))}")
    if apply:
        lam.update_function_configuration(FunctionName=name, Environment={'Variables': variables})
        _wait(lam, name)


def domain(clients, apply):
    lam = clients['lambda']
    pack()
    for name in LIVE_FUNCTIONS + ORG_FUNCTIONS:  # _logging.py (CORS defaults) ships in every Python zip
        if _exists(lam, name):
            _update_code(lam, name, apply)
    for name, updates in DOMAIN_ENV.items():
        if _exists(lam, name):
            _merge_env(lam, name, updates, apply)
        else:
            print(f'  skip env {name} (no such function; run --step deploy first)')


STEP_FNS = {'deploy': deploy, 'migrate-routes': migrate_routes, 'remigrate': remigrate, 'domain': domain}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--step', choices=STEPS, required=True)
    ap.add_argument('--apply', action='store_true', help='perform writes (default: dry run)')
    ap.add_argument('--endpoint', help='AWS endpoint URL, e.g. Floci http://localhost:4567 (default: live AWS)')
    args = ap.parse_args(argv)
    if args.apply and not args.endpoint and os.environ.get('ROLLOUT_LIVE') != '1':
        print('Refusing a live --apply: pass --endpoint, or set ROLLOUT_LIVE=1 for the real rollout.', file=sys.stderr)
        return 2
    if args.endpoint:
        for name in local_api._NEVER:
            os.environ.pop(name, None)
        os.environ.update({k: local_api.AWS_ENV[k] for k in (
            'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 'AWS_REGION')})
        os.environ['AWS_ENDPOINT_URL'] = args.endpoint
    os.environ['AWS_PAGER'] = ''
    import boto3
    clients = {'lambda': boto3.client('lambda'), 'apigateway': boto3.client('apigateway')}
    print(f"{'APPLY' if args.apply else 'DRY RUN'} {args.step} on {args.endpoint or 'live AWS'}", flush=True)
    STEP_FNS[args.step](clients, args.apply)
    return 0


if __name__ == '__main__':
    sys.exit(main())
