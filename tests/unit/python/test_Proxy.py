"""AC1 no retried writes; AC3 ETag/X-Request-Id exposed; AC4 one request ID end to end."""
import importlib
import io
import json
import os
import sys
import urllib.error

import pytest

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda'))


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setenv('API_ENDPOINT', 'http://upstream.invalid')
    monkeypatch.setenv('API_KEY', 'k')
    monkeypatch.setenv('JWT_SECRET', 's')
    monkeypatch.setenv('LOG_STDOUT', '0')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.syspath_prepend(LAMBDA_DIR)
    for name in ('_logging', '_org', 'Proxy'):
        sys.modules.pop(name, None)
    return importlib.import_module('Proxy')


class _Upstream:
    """Fake urlopen: records requests, replays a scripted outcome."""
    def __init__(self, outcome):
        self.outcome, self.requests = outcome, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        return self.outcome(req)


def _http_error(code, headers=None, body=b'{}'):
    def raise_it(req):
        raise urllib.error.HTTPError(req.full_url, code, 'x', headers or {}, io.BytesIO(body))
    return raise_it


def _timeout(req):
    raise TimeoutError('timed out')


class _Ok:
    status = 200
    headers = {'ETag': '7'}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": true}'


@pytest.mark.parametrize('outcome', [_http_error(503), _timeout])
@pytest.mark.parametrize('method,calls', [('POST', 1), ('PUT', 1), ('PATCH', 1), ('DELETE', 1), ('GET', 2)])
def test_only_safe_methods_retry(proxy, monkeypatch, outcome, method, calls):
    up = _Upstream(outcome)
    monkeypatch.setattr(proxy.urllib.request, 'urlopen', up)
    res = proxy._forward({'body': '{}'}, '/items', method, user_id='u@x.co', rid='r1')
    assert len(up.requests) == calls
    assert res['statusCode'] >= 500


def test_upstream_etag_and_request_id_forwarded(proxy, monkeypatch):
    up = _Upstream(lambda req: _Ok())
    monkeypatch.setattr(proxy.urllib.request, 'urlopen', up)
    res = proxy._forward({}, '/items/1', 'PUT', user_id='u@x.co', rid='abc123')
    assert res['headers']['ETag'] == '7'
    assert up.requests[0].get_header('X-request-id') == 'abc123'
    assert 'ETag' in res['headers']['Access-Control-Expose-Headers']
    assert 'X-Request-Id' in res['headers']['Access-Control-Expose-Headers']


def test_412_passes_etag_through(proxy, monkeypatch):
    up = _Upstream(_http_error(412, {'ETag': '4'}, b'{"item": {"version": 4}}'))
    monkeypatch.setattr(proxy.urllib.request, 'urlopen', up)
    res = proxy._forward({}, '/items/1', 'PUT', user_id='u@x.co', rid='r1')
    assert res['statusCode'] == 412 and res['headers']['ETag'] == '4'
    assert json.loads(res['body'])['item']['version'] == 4


def test_every_response_carries_client_request_id(proxy, monkeypatch, capsys):
    monkeypatch.setattr(proxy._logging, '_LOG_STDOUT', True)
    event = {'httpMethod': 'GET', 'pathParameters': {'proxy': 'items'},
             'headers': {'X-Request-Id': 'abc123'}, 'requestContext': {'requestId': 'gw-1'}}
    res = proxy.lambda_handler(event, None)
    assert res['statusCode'] == 401
    assert res['headers']['X-Request-Id'] == 'abc123'
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert lines and all(l['requestId'] == 'abc123' for l in lines)


def test_generated_request_id_matches_log_line(proxy, monkeypatch, capsys):
    monkeypatch.setattr(proxy._logging, '_LOG_STDOUT', True)
    res = proxy.lambda_handler({'httpMethod': 'OPTIONS', 'headers': {}}, None)
    rid = res['headers']['X-Request-Id']
    assert rid and json.loads(capsys.readouterr().out.splitlines()[-1])['requestId'] == rid


INVITE = 'org-invites/tok-SECRET123/accept'


def test_invite_token_never_logged(proxy, monkeypatch, capsys):
    """SEC-1: the raw invite token stays out of every Proxy log line and Sentry tag."""
    monkeypatch.setattr(proxy._logging, '_LOG_STDOUT', True)
    tags = {}

    class Scope:
        def set_tag(self, k, v):
            tags[k] = v

    class FakeSentry:
        @staticmethod
        def push_scope():
            import contextlib
            return contextlib.nullcontext(Scope())

        @staticmethod
        def capture_exception(exc):
            pass

    monkeypatch.setattr(proxy._logging, 'sentry_sdk', FakeSentry)
    monkeypatch.setattr(proxy.urllib.request, 'urlopen', _Upstream(_timeout))
    proxy.lambda_handler({'httpMethod': 'POST', 'pathParameters': {'proxy': INVITE}, 'headers': {}}, None)
    proxy._forward({'pathParameters': {'proxy': INVITE}}, f'/{INVITE}', 'POST', user_id='u@x.co', rid='r1')
    out = capsys.readouterr().out
    assert 'org-invites/{token}/accept' in out
    assert 'SECRET123' not in out and 'SECRET123' not in json.dumps(tags)
    assert tags['path'] == '/org-invites/{token}/accept'


def test_browser_may_send_request_id(proxy):
    assert 'X-Request-Id' in proxy._CORS_STATIC['Access-Control-Allow-Headers'].split(',')
