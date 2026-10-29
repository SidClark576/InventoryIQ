"""Local API runner: route table, x-api-key gate, offline barcode stub (no Floci needed)."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

import local_api  # noqa: E402


def _calls(monkeypatch):
    calls = []

    def fake_handler(module):
        return lambda event, context: calls.append((module, event)) or {'statusCode': 200, 'body': ''}

    monkeypatch.setattr(local_api, 'handler', fake_handler)
    monkeypatch.setattr(local_api, 'api_key', lambda: 'k')
    return calls


def test_backend_routes_hit_their_handler_with_decoded_path_parameters(monkeypatch):
    calls = _calls(monkeypatch)
    cases = [
        ('GET', '/items', 'GetAllItems', None),
        ('POST', '/items', 'AddItem', None),
        ('POST', '/items/import', 'BulkImport', None),
        ('PUT', '/items/a%2Fb', 'UpdateItem', {'itemID': 'a/b'}),
        ('DELETE', '/items/x1', 'DeleteItem', {'itemID': 'x1'}),
        ('POST', '/items/x1/restore', 'RestoreItem', {'itemID': 'x1'}),
        ('GET', '/import/presign', 'BulkImport', None),
        ('GET', '/import/j1', 'BulkImport', {'jobId': 'j1'}),
        ('GET', '/insights', 'LowItemInsight', None),
        ('GET', '/transactions', 'GetTransactions', None),
        ('GET', '/categories', 'GetCategories', None),
        ('DELETE', '/categories/Canned%20Goods', 'DeleteCategory', {'categoryName': 'Canned Goods'}),
        ('GET', '/barcode/4800000000017', 'BarcodeLookup', {'code': '4800000000017'}),
        ('GET', '/orgs', 'Orgs', None),
        ('POST', '/orgs/o1/switch', 'Orgs', {'id': 'o1'}),
        ('GET', '/orgs/o1/members', 'OrgMembers', {'id': 'o1'}),
        ('POST', '/orgs/o1/invites', 'OrgInvites', {'id': 'o1'}),
        ('POST', '/org-invites/t%2B1/accept', 'OrgInvites', {'token': 't+1'}),
    ]
    for method, path, module, params in cases:
        res = local_api.route(method, '/_backend' + path, {'x-api-key': 'k'}, None, None)
        assert res['statusCode'] == 200, path
        got_module, event = calls[-1]
        assert got_module == module, path
        assert event['pathParameters'] == params, path
        assert event['path'] == path and event['httpMethod'] == method


def test_backend_without_or_with_wrong_api_key_is_403(monkeypatch):
    calls = _calls(monkeypatch)
    assert local_api.route('GET', '/_backend/items', {}, None, None)['statusCode'] == 403
    assert local_api.route('GET', '/_backend/items', {'x-api-key': 'nope'}, None, None)['statusCode'] == 403
    assert calls == []


def test_backend_key_check_fails_closed_when_secret_missing(monkeypatch):
    calls = _calls(monkeypatch)
    monkeypatch.setattr(local_api, 'api_key', lambda: '')
    assert local_api.route('GET', '/_backend/items', {'x-api-key': ''}, None, None)['statusCode'] == 403
    assert calls == []


def test_unknown_routes_are_404(monkeypatch):
    calls = _calls(monkeypatch)
    for method, path in [('GET', '/_backend/nope'), ('PATCH', '/_backend/items'), ('GET', '/elsewhere')]:
        assert local_api.route(method, path, {'x-api-key': 'k'}, None, None)['statusCode'] == 404, path
    assert calls == []


def test_proxy_route_calls_proxy_with_raw_sub_path(monkeypatch):
    calls = _calls(monkeypatch)
    local_api.route('GET', '/proxy/categories/Canned%20Goods', {}, None, None)
    module, event = calls[-1]
    assert module == 'Proxy' and event['pathParameters'] == {'proxy': 'categories/Canned%20Goods'}


def test_setup_installs_offline_barcode_lookups(monkeypatch):
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    local_api.setup()
    import BarcodeLookup
    assert BarcodeLookup._lookup_off is local_api.offline_lookup
    assert BarcodeLookup._lookup_upc is local_api.offline_lookup
    assert os.environ['AWS_ENDPOINT_URL'] == 'http://localhost:4566'
    assert not any('moto' in k.lower() or 'moto' in v.lower() for k, v in local_api.AWS_ENV.items())
    assert 'SENTRY_DSN' not in os.environ and 'AWS_PROFILE' not in os.environ


def test_backend_route_passes_query_string_parameters(monkeypatch):
    calls = _calls(monkeypatch)
    local_api.route('GET', '/_backend/transactions', {'x-api-key': 'k'}, None, {'since': '2026-10-01T00:00:00Z'})
    module, event = calls[-1]
    assert module == 'GetTransactions' and event['queryStringParameters'] == {'since': '2026-10-01T00:00:00Z'}


def _uri(fn):
    return f'arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:0:function:{fn}/invocations'


def _res(path, **methods):
    return {'path': path, 'resourceMethods': {
        m: {'methodIntegration': {'type': kind, 'uri': _uri(fn) if fn else ''}} for m, (kind, fn) in methods.items()}}


def test_routes_from_gateway_maps_lambda_methods_to_handler_modules():
    resources = [
        {'path': '/'},
        _res('/items', GET=('AWS_PROXY', 'GetAllItems'), OPTIONS=('MOCK', None)),
        _res('/items/{itemID}/restore', POST=('AWS_PROXY', 'RestoreItem'), OPTIONS=('MOCK', None)),
        _res('/ping', GET=('MOCK', None), POST=('HTTP_PROXY', None)),
    ]
    handlers = {'GetAllItems': 'GetAllItems.lambda_handler', 'RestoreItem': 'lambda_function.lambda_handler'}
    assert local_api.routes_from_gateway(resources, handlers) == [
        ('GET', '/items', 'GetAllItems'), ('POST', '/items/{itemID}/restore', 'lambda_function')]


class _Gateway:
    def __init__(self):
        self.deployment, self.resources, self.handlers, self.resource_reads = 'd1', [], {}, 0

    def get_rest_apis(self, **_):
        return {'items': [{'id': 'other', 'name': 'Other'}, {'id': 'api1', 'name': 'InventoryIQ-API'}]}

    def get_stage(self, restApiId, stageName):
        assert (restApiId, stageName) == ('api1', 'prod')
        return {'deploymentId': self.deployment}

    def get_resources(self, restApiId, embed, **_):
        assert restApiId == 'api1' and embed == ['methods']
        self.resource_reads += 1
        return {'items': list(self.resources)}

    def list_functions(self, **_):
        return {'Functions': [{'FunctionName': f, 'Handler': h} for f, h in self.handlers.items()]}


def _gateway(monkeypatch):
    fake = _Gateway()
    monkeypatch.setenv('LOCAL_API_GATEWAY', '1')
    monkeypatch.setattr(local_api, '_aws', lambda name: fake)
    monkeypatch.setattr(local_api, '_deployed', {'id': None, 'resources': []})
    fake.resources = [_res('/items', GET=('AWS_PROXY', 'GetAllItems'), OPTIONS=('MOCK', None)),
                      _res('/items/{itemID}/restore', POST=('AWS_PROXY', 'RestoreItem'))]
    fake.handlers = {'GetAllItems': 'GetAllItems.lambda_handler', 'RestoreItem': 'lambda_function.lambda_handler'}
    return fake


def _status(method, path):
    return local_api.route(method, '/_backend' + path, {'x-api-key': 'k'}, None, None)['statusCode']


def test_gateway_mode_serves_only_the_deployed_prod_stage(monkeypatch):
    calls = _calls(monkeypatch)
    fake = _gateway(monkeypatch)
    assert _status('GET', '/items') == 200 and calls[-1][0] == 'GetAllItems'
    assert _status('GET', '/orgs') == 404  # not in the API
    assert _status('POST', '/items/import') == 404  # in the static table, not live
    assert _status('OPTIONS', '/items') == 404  # MOCK method ignored
    fake.resources.append(_res('/orgs', GET=('AWS_PROXY', 'Orgs')))
    fake.handlers['Orgs'] = 'Orgs.lambda_handler'
    assert _status('GET', '/orgs') == 404  # added but not deployed
    fake.deployment = 'd2'
    assert _status('GET', '/orgs') == 200 and calls[-1][0] == 'Orgs'
    assert _status('GET', '/items') == 200 and fake.resource_reads == 2  # refetched once per deployment


def test_gateway_mode_lambda_function_handler_is_502_until_the_handler_is_fixed(monkeypatch):
    fake = _gateway(monkeypatch)
    monkeypatch.setattr(local_api, 'api_key', lambda: 'k')
    res = local_api.route('POST', '/_backend/items/x1/restore', {'x-api-key': 'k'}, None, None)
    assert res['statusCode'] == 502 and json.loads(res['body']) == {'message': 'Internal server error'}
    calls = _calls(monkeypatch)
    fake.handlers['RestoreItem'] = 'RestoreItem.lambda_handler'  # takes effect without a redeploy, as live
    assert _status('POST', '/items/x1/restore') == 200 and calls[-1][0] == 'RestoreItem'


def test_static_table_when_gateway_env_unset(monkeypatch):
    calls = _calls(monkeypatch)
    monkeypatch.delenv('LOCAL_API_GATEWAY', raising=False)
    monkeypatch.setattr(local_api, '_aws', lambda name: pytest.fail('gateway read'))
    assert _status('POST', '/items/import') == 200 and calls[-1][0] == 'BulkImport'
