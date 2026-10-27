"""AC5 logs on by default; request IDs; AC6 capture_error tags user/org/request."""
import contextlib
import importlib
import json
import os
import sys

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda'))


def _load(monkeypatch, log_stdout=None):
    monkeypatch.syspath_prepend(LAMBDA_DIR)
    if log_stdout is None:
        monkeypatch.delenv('LOG_STDOUT', raising=False)
    else:
        monkeypatch.setenv('LOG_STDOUT', log_stdout)
    sys.modules.pop('_logging', None)
    return importlib.import_module('_logging')


def test_log_json_prints_by_default(monkeypatch, capsys):
    _load(monkeypatch).log_json(function='T', status=200)
    assert json.loads(capsys.readouterr().out)['status'] == 200


def test_log_stdout_zero_silences(monkeypatch, capsys):
    _load(monkeypatch, '0').log_json(function='T')
    assert capsys.readouterr().out == ''


def test_request_id_prefers_valid_client_header(monkeypatch):
    lg = _load(monkeypatch)
    ctx = {'requestContext': {'requestId': 'gw-1'}}
    assert lg.request_id({**ctx, 'headers': {'X-Request-Id': 'abc123'}}) == 'abc123'
    assert lg.request_id({**ctx, 'headers': {'x-request-id': 'bad id!'}}) == 'gw-1'
    assert lg.request_id({**ctx, 'headers': {'x-request-id': 'a' * 65}}) == 'gw-1'
    assert len(lg.request_id({})) == 36


def test_log_json_uses_header_request_id(monkeypatch, capsys):
    lg = _load(monkeypatch)
    lg.log_json(event={'headers': {'x-request-id': 'abc123'}, 'requestContext': {'requestId': 'gw-1'}})
    assert json.loads(capsys.readouterr().out)['requestId'] == 'abc123'


class _FakeSentry:
    def __init__(self):
        self.tags, self.captured = {}, []

    @contextlib.contextmanager
    def push_scope(self):
        fake = self

        class Scope:
            def set_tag(self, k, v):
                fake.tags[k] = v
        yield Scope()

    def capture_exception(self, exc):
        self.captured.append(exc)


def test_capture_error_tags_from_event(monkeypatch, capsys):
    lg = _load(monkeypatch)
    fake = _FakeSentry()
    monkeypatch.setattr(lg, 'sentry_sdk', fake)
    exc = ValueError('secret detail')
    event = {'headers': {'x-iq-user': 'a@b.co', 'x-iq-org': 'org-1', 'x-request-id': 'abc123'}}
    lg.capture_error(exc, event=event, step='items')
    assert fake.captured == [exc]
    assert fake.tags == {'requestId': 'abc123', 'userID_hash': lg.hash_user('a@b.co'),
                         'orgID': 'org-1', 'step': 'items'}
    assert 'secret detail' not in capsys.readouterr().out


def test_server_error_is_generic(monkeypatch):
    lg = _load(monkeypatch, '0')
    res = lg.server_error(RuntimeError('boom'), {'headers': {}}, {'X': '1'})
    assert res['statusCode'] == 500 and res['headers'] == {'X': '1'}
    assert json.loads(res['body']) == {'error': 'Internal Server Error', 'code': 'INTERNAL'}


def test_sentry_event_drops_secrets(monkeypatch):
    """SEC note round 2: Sentry request context must not carry the session JWT or a raw invite token."""
    monkeypatch.syspath_prepend(os.path.join(LAMBDA_DIR, 'python_vendor'))
    import sentry_sdk
    seen = {}
    monkeypatch.setattr(sentry_sdk, 'init', lambda **kw: seen.update(kw))
    monkeypatch.setenv('SENTRY_DSN', 'https://k@example.invalid/1')
    log = _load(monkeypatch)
    assert seen['before_send'] is log._scrub_event
    assert seen['before_send_transaction'] is log._scrub_event
    assert not seen.get('traces_sample_rate')  # SEC-2: no tracing, transactions would carry request headers
    event = {'request': {
        'url': 'https://api.example/prod/proxy/org-invites/SECRETINVITE/accept',
        'query_string': 'next=org-invites/SECRETINVITE/accept',
        'headers': {'X-Session-Token': 'JWT123', 'Authorization': 'Bearer JWT123',
                    'Cookie': 's=JWT123', 'Content-Type': 'application/json'},
    }}
    out = json.dumps(log._scrub_event(event, {}))
    assert 'JWT123' not in out and 'SECRETINVITE' not in out
    assert event['request']['headers'] == {'Content-Type': 'application/json'}
    assert 'org-invites/{token}/accept' in event['request']['url']
    assert log._scrub_event({'message': 'x'}, {}) == {'message': 'x'}


def test_scrub_redacts_breadcrumb_invite_tokens(monkeypatch):
    log = _load(monkeypatch)
    event = {'breadcrumbs': {'values': [
        {'category': 'httplib', 'data': {'url': 'https://api/org-invites/SECRETINVITE/accept'}},
        {'message': 'POST /org-invites/SECRETINVITE/accept'},
        {'data': None}]}}
    out = json.dumps(log._scrub_event(event, {}))
    assert 'SECRETINVITE' not in out and out.count('org-invites/{token}/accept') == 2


def test_plain_keeps_integers_integral(monkeypatch):
    from decimal import Decimal
    out = _load(monkeypatch).plain({'quantity': Decimal(10), 'price': Decimal('9.5'), 'name': 'Rice'})
    assert json.dumps(out) == '{"quantity": 10, "price": 9.5, "name": "Rice"}'


def test_number_field(monkeypatch):
    from decimal import Decimal
    nf = _load(monkeypatch).number_field
    assert nf({}, 'price', default=Decimal(0)) == (Decimal(0), None)
    assert nf({'price': '9.5'}, 'price') == (Decimal('9.5'), None)
    assert nf({'quantity': 4.0}, 'quantity', integer=True) == (4, None)
    for value, integer in ((-1, False), ('abc', False), (True, True), (1.5, True), (None, False), ('NaN', False)):
        val, err = nf({'qty': value}, 'qty', integer=integer)
        assert val is None and err['statusCode'] == 400, value
        assert json.loads(err['body'])['code'] == 'INVALID_FIELD' and json.loads(err['body'])['field'] == 'qty'


def test_number_field_rejects_huge_exponents(monkeypatch):
    """SEC-1: int(Decimal('1e10000000')) pins the CPU; huge exponents must fail before int()."""
    nf = _load(monkeypatch).number_field
    for value, integer in (('1e16', True), ('1e400', False), ('1e10000000', True)):
        val, err = nf({'qty': value}, 'qty', integer=integer)
        assert val is None and err['statusCode'] == 400, value

def test_json_body(monkeypatch):
    jb = _load(monkeypatch).json_body
    assert jb({'body': None}) == ({}, None)
    assert jb({'body': '{"a": 1}'}) == ({'a': 1}, None)
    for raw in ('{bad', '[1]', '5'):
        body, err = jb({'body': raw})
        assert body is None and json.loads(err['body'])['code'] == 'INVALID_JSON', raw
