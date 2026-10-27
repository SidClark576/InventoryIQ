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
