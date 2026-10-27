"""Local API runner: route table, x-api-key gate, offline barcode stub (no Floci needed)."""
import os
import sys
from pathlib import Path

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
