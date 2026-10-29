"""scripts/rollout_orgs.py against moto: dry run writes nothing, deploy, migrate + routes, remigrate, domain, live guard."""
import base64
import hashlib
import io
import os
import sys
import zipfile
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

import rollout_orgs  # noqa: E402

OWNER = 'u@x.co'
OLD_HANDLER = ('RestoreItem', 'PurgeDeletedItems')


def _zip(body):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('x.py', body)
    return buf.getvalue()


OLD_ZIP, NEW_ZIP = _zip('old = 1'), _zip('new = 1')


def _sha(data):
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def _table(ddb, name, keys, gsi=None):
    extra = {'GlobalSecondaryIndexes': [{'IndexName': f'{gsi}-index', 'KeySchema': [
        {'AttributeName': gsi, 'KeyType': 'HASH'}], 'Projection': {'ProjectionType': 'ALL'}}]} if gsi else {}
    attrs = list(dict.fromkeys(keys + ([gsi] if gsi else [])))
    ddb.create_table(TableName=name, BillingMode='PAY_PER_REQUEST',
                     KeySchema=[{'AttributeName': k, 'KeyType': t} for k, t in zip(keys, ('HASH', 'RANGE'))],
                     AttributeDefinitions=[{'AttributeName': a, 'AttributeType': 'S'} for a in attrs], **extra)
    return ddb.Table(name)


@pytest.fixture
def aws(monkeypatch):
    for k, v in {'AWS_DEFAULT_REGION': 'us-east-1', 'AWS_ACCESS_KEY_ID': 'testing',
                 'AWS_SECRET_ACCESS_KEY': 'testing', 'ROLLOUT_LIVE': '1'}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)
    monkeypatch.setattr(rollout_orgs, 'pack', lambda: None)
    monkeypatch.setattr(rollout_orgs, 'zip_bytes', lambda name: NEW_ZIP)
    with mock_aws():
        role = boto3.client('iam').create_role(RoleName='lambda', AssumeRolePolicyDocument='{}')['Role']['Arn']
        lam = boto3.client('lambda')
        for name in rollout_orgs.LIVE_FUNCTIONS:
            handler = 'lambda_function.lambda_handler' if name in OLD_HANDLER else f'{name}.lambda_handler'
            env = {'Variables': {'SENTRY_DSN': 'dsn-secret', 'API_KEY_SECRET': 'other'}} if name == 'AddItem' else {}
            lam.create_function(FunctionName=name, Runtime='python3.12', Role=role, Handler=handler,
                                Code={'ZipFile': OLD_ZIP}, Timeout=15, MemorySize=256, Environment=env)
        gw = boto3.client('apigateway')
        api = gw.create_rest_api(name='InventoryIQ-API')['id']
        root = gw.get_resources(restApiId=api)['items'][0]['id']
        items = gw.create_resource(restApiId=api, parentId=root, pathPart='items')['id']
        gw.put_method(restApiId=api, resourceId=items, httpMethod='GET', authorizationType='NONE')
        gw.put_integration(restApiId=api, resourceId=items, httpMethod='GET', type='MOCK')
        gw.create_deployment(restApiId=api, stageName='prod')
        ddb = boto3.resource('dynamodb')
        _table(ddb, 'Users', ['Email']).put_item(Item={'Email': OWNER})
        _table(ddb, 'Organizations', ['orgID'])
        _table(ddb, 'OrgMembers', ['orgID', 'userID'], 'userID')
        _table(ddb, 'InventoryIQ', ['itemID']).put_item(Item={'itemID': 'i1', 'userID': OWNER})
        _table(ddb, 'InventoryTransactions', ['transactionID']).put_item(Item={'transactionID': 't1', 'userID': OWNER})
        yield {'lambda': lam, 'apigateway': gw, 'api': api, 'ddb': ddb}


def _state(aws):
    lam, gw, api = aws['lambda'], aws['apigateway'], aws['api']
    fns = {f['FunctionName']: (f['Handler'], f['CodeSha256'], str(f.get('Environment')))
           for f in lam.list_functions()['Functions']}
    resources = sorted((r['path'], tuple(sorted(r.get('resourceMethods') or {})))
                       for r in gw.get_resources(restApiId=api)['items'])
    deployments = len(gw.get_deployments(restApiId=api)['items'])
    data = [sorted(map(str, aws['ddb'].Table(t).scan()['Items']))
            for t in ('Organizations', 'OrgMembers', 'InventoryIQ', 'InventoryTransactions')]
    return fns, resources, deployments, data


def _run(*argv):
    assert rollout_orgs.main(list(argv)) == 0


def test_dry_run_of_every_step_prints_calls_and_writes_nothing(aws, capsys):
    before = _state(aws)
    for step in rollout_orgs.STEPS:
        _run('--step', step)
    assert _state(aws) == before
    out = capsys.readouterr().out
    assert 'DRY RUN' in out and 'update code AddItem' in out and 'create function Orgs' in out
    assert 'GET /orgs -> Orgs' in out and 'deploy stage prod' in out
    assert 'set env Authentication: APP_URL, CORS_ORIGIN, SES_SENDER' in out and 'skip env OrgInvites' in out


def test_deploy_updates_fixes_handlers_creates_org_functions_and_adds_no_route(aws, capsys):
    routes_before = _state(aws)[1]
    _run('--step', 'deploy', '--apply')
    lam = aws['lambda']
    for name in rollout_orgs.LIVE_FUNCTIONS:
        conf = lam.get_function_configuration(FunctionName=name)
        assert conf['CodeSha256'] == _sha(NEW_ZIP), name
        assert conf['Handler'] == f'{name}.lambda_handler', name
    add = lam.get_function_configuration(FunctionName='AddItem')
    for name in rollout_orgs.ORG_FUNCTIONS:
        conf = lam.get_function_configuration(FunctionName=name)
        assert conf['Handler'] == f'{name}.lambda_handler'
        assert [conf[k] for k in ('Runtime', 'Role', 'Timeout', 'MemorySize')] == \
            [add[k] for k in ('Runtime', 'Role', 'Timeout', 'MemorySize')]
        assert conf['Environment']['Variables'] == {'SENTRY_DSN': 'dsn-secret'}
    first = _state(aws)
    assert first[1] == routes_before
    _run('--step', 'deploy', '--apply')
    assert _state(aws) == first
    out = capsys.readouterr().out
    assert 'dsn-secret' not in out
    rerun = out.rsplit('APPLY deploy', 1)[1]
    assert 'create function' not in rerun and 'set handler' not in rerun


def test_migrate_routes_stamps_adds_routes_and_permissions_redeploys_then_remigrate_stamps_zero(aws, capsys):
    _run('--step', 'deploy', '--apply')
    gw, api, lam = aws['apigateway'], aws['api'], aws['lambda']
    stage_before = gw.get_stage(restApiId=api, stageName='prod')['deploymentId']
    _run('--step', 'migrate-routes', '--apply')
    assert aws['ddb'].Table('InventoryIQ').get_item(Key={'itemID': 'i1'})['Item'].get('orgID')
    assert aws['ddb'].Table('InventoryTransactions').get_item(Key={'transactionID': 't1'})['Item'].get('orgID')
    by_path = {r['path']: r for r in gw.get_resources(restApiId=api)['items']}
    for method, path, module in rollout_orgs.ORG_ROUTES:
        m = gw.get_method(restApiId=api, resourceId=by_path[path]['id'], httpMethod=method)
        assert m['apiKeyRequired'] is True
        assert m['methodIntegration']['type'] == 'AWS_PROXY'
        assert f':function:{module}/invocations' in m['methodIntegration']['uri']
    for name in rollout_orgs.ORG_FUNCTIONS:
        assert 'apigateway.amazonaws.com' in lam.get_policy(FunctionName=name)['Policy']
    assert gw.get_stage(restApiId=api, stageName='prod')['deploymentId'] != stage_before
    out = capsys.readouterr().out
    assert out.count('APPLIED:') == 2 and '2 items to stamp' in out
    _run('--step', 'migrate-routes', '--apply')  # rerun: methods and permissions already there
    _run('--step', 'remigrate', '--apply')
    assert 'APPLIED: 0 orgs to create, 0 items to stamp' in capsys.readouterr().out.rsplit('APPLY remigrate', 1)[1]


def test_domain_updates_code_and_merges_only_its_env_keys(aws, capsys):
    _run('--step', 'deploy', '--apply')
    lam = aws['lambda']
    keep = {'JWT_SECRET': 'jwt-secret', 'SENTRY_DSN': 'dsn-secret', 'CORS_ORIGIN': 'https://old.example'}
    lam.update_function_configuration(FunctionName='Authentication', Environment={'Variables': keep})
    lam.update_function_code(FunctionName='Orgs', ZipFile=OLD_ZIP)
    _run('--step', 'domain', '--apply')
    env = {n: lam.get_function_configuration(FunctionName=n).get('Environment', {}).get('Variables', {})
           for n in rollout_orgs.LIVE_FUNCTIONS + rollout_orgs.ORG_FUNCTIONS}
    new = {'CORS_ORIGIN': rollout_orgs.CORS_ORIGIN, 'APP_URL': 'https://app.panindo.app',
           'SES_SENDER': 'noreply@panindo.app'}
    assert env['Authentication'] == {**keep, **new}
    assert env['OrgInvites'] == {'SENTRY_DSN': 'dsn-secret', 'APP_URL': new['APP_URL'], 'SES_SENDER': new['SES_SENDER']}
    assert env['Proxy'] == {'CORS_ORIGIN': new['CORS_ORIGIN']}
    assert env['AddItem'] == {'SENTRY_DSN': 'dsn-secret', 'API_KEY_SECRET': 'other'}
    assert lam.get_function_configuration(FunctionName='Orgs')['CodeSha256'] == _sha(NEW_ZIP)
    out = capsys.readouterr().out.rsplit('APPLY domain', 1)[1]
    assert 'update code Orgs' in out and 'set env OrgInvites: APP_URL, SES_SENDER' in out
    for value in [*keep.values(), *new.values()]:
        assert value not in out


def test_apply_without_endpoint_refuses_live_before_any_client(monkeypatch):
    monkeypatch.delenv('ROLLOUT_LIVE', raising=False)

    def no_client(*a, **k):
        raise AssertionError('client built')

    monkeypatch.setattr(boto3, 'client', no_client)
    monkeypatch.setattr(boto3, 'resource', no_client)
    for step in rollout_orgs.STEPS:
        assert rollout_orgs.main(['--step', step, '--apply']) == 2


def test_endpoint_points_at_local_fake_keys_and_drops_profile(monkeypatch):
    monkeypatch.setattr(os, 'environ', dict(os.environ, AWS_PROFILE='inventoryiq'))
    seen = []
    monkeypatch.setitem(rollout_orgs.STEP_FNS, 'remigrate', lambda clients, apply: seen.append(dict(os.environ)))
    assert rollout_orgs.main(['--endpoint', 'http://localhost:4567', '--step', 'remigrate', '--apply']) == 0
    env = seen[0]
    assert env['AWS_ENDPOINT_URL'] == 'http://localhost:4567' and env['AWS_ACCESS_KEY_ID'] == 'local'
    assert 'AWS_PROFILE' not in env
