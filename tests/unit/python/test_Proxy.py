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


# ── PROXY_MODE=invoke: direct lambda:InvokeFunction (job 017) ─────────────────
from conftest import jwt_for  # noqa: E402

OK = {'statusCode': 200, 'headers': {'ETag': '5', 'X-Other': 'no'}, 'body': '[]'}


class _Lambda:
    """Fake _invoke_lambda: records (name, event), replays scripted outcomes (the last one repeats)."""
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def __call__(self, name, event):
        self.calls.append((name, event))
        out = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture
def invoke_proxy(proxy, monkeypatch):
    monkeypatch.setattr(proxy, 'PROXY_MODE', 'invoke')
    return proxy


def test_invoke_sends_each_route_a_gateway_event_with_trusted_headers_only(invoke_proxy, monkeypatch):
    import _routes
    fn = _Lambda(OK)
    monkeypatch.setattr(invoke_proxy, '_invoke_lambda', fn)
    client = {'x-iq-user': 'evil@x.co', 'X-IQ-Org': 'o2', 'x-iq-role': 'owner', 'x-api-key': 'leak',
              'If-Match': '3', 'idempotency-key': 'i1', 'x-session-token': 't'}
    for method, resource, name in _routes.ROUTES:
        segs = [s[1:-1] if s.startswith('{') else s for s in resource.split('/')]
        path = '/'.join(segs)
        params = {s[1:-1]: s[1:-1] for s in resource.split('/') if s.startswith('{')} or None
        event = {'headers': client, 'body': '{}', 'queryStringParameters': {'q': '1'}}
        res = invoke_proxy._invoke(event, path, method, user_id='u@x.co', org_id='o1', role='editor', rid='r1')
        assert res['statusCode'] == 200, resource
        assert fn.calls[-1] == (name, {
            'httpMethod': method, 'path': path, 'resource': resource, 'pathParameters': params,
            'queryStringParameters': {'q': '1'}, 'body': '{}',
            'headers': {'content-type': 'application/json', 'x-request-id': 'r1', 'x-iq-user': 'u@x.co',
                        'x-iq-org': 'o1', 'x-iq-role': 'editor', 'if-match': '3', 'idempotency-key': 'i1'}})


def test_invoke_decodes_path_parameters(invoke_proxy, monkeypatch):
    fn = _Lambda(OK)
    monkeypatch.setattr(invoke_proxy, '_invoke_lambda', fn)
    invoke_proxy._invoke({}, '/categories/Canned%20Goods', 'DELETE', user_id='u@x.co', rid='r1')
    assert fn.calls[-1][0] == 'DeleteCategory'
    assert fn.calls[-1][1]['pathParameters'] == {'categoryName': 'Canned Goods'}
    assert 'x-iq-org' not in fn.calls[-1][1]['headers']


@pytest.mark.parametrize('method,path,calls', [('GET', '/items', 2), ('POST', '/items', 1),
                                               ('PUT', '/items/1', 1), ('DELETE', '/items/1', 1)])
def test_invoke_retries_only_safe_methods_then_502(invoke_proxy, monkeypatch, method, path, calls):
    fn = _Lambda(RuntimeError('boom'))
    monkeypatch.setattr(invoke_proxy, '_invoke_lambda', fn)
    res = invoke_proxy._invoke({}, path, method, user_id='u@x.co', rid='r1')
    assert len(fn.calls) == calls
    assert res['statusCode'] == 502 and json.loads(res['body']) == {'message': 'Internal server error'}


def test_invoke_get_succeeds_on_retry(invoke_proxy, monkeypatch):
    monkeypatch.setattr(invoke_proxy, '_invoke_lambda', _Lambda(RuntimeError('boom'), OK))
    assert invoke_proxy._invoke({}, '/items', 'GET', user_id='u@x.co', rid='r1')['statusCode'] == 200


def test_invoke_unknown_route_is_404_without_invoking(invoke_proxy, monkeypatch):
    fn = _Lambda(OK)
    monkeypatch.setattr(invoke_proxy, '_invoke_lambda', fn)
    for method, path in [('GET', '/nope'), ('PATCH', '/items'), ('POST', '/auth/login')]:
        res = invoke_proxy._invoke({}, path, method, user_id='u@x.co', rid='r1')
        assert res['statusCode'] == 404 and json.loads(res['body']) == {'message': 'Not Found'}
    assert fn.calls == []


def test_invoke_passes_status_body_and_only_the_etag_through(invoke_proxy, monkeypatch):
    monkeypatch.setattr(invoke_proxy, '_invoke_lambda', _Lambda({**OK, 'statusCode': 412}))
    res = invoke_proxy._invoke({}, '/items/1', 'PUT', user_id='u@x.co', rid='r1')
    assert res['statusCode'] == 412 and res['body'] == '[]'
    assert res['headers']['ETag'] == '5' and 'X-Other' not in res['headers']
    assert res['headers']['Access-Control-Expose-Headers'] == invoke_proxy._CORS_STATIC['Access-Control-Expose-Headers']


class _LambdaClient:
    def __init__(self, response):
        self.response, self.calls = response, []

    def invoke(self, **kw):
        self.calls.append(kw)
        return {**self.response, 'Payload': io.BytesIO(self.response['Payload'])}


def test_invoke_lambda_returns_payload_and_raises_on_function_error(proxy, monkeypatch):
    client = _LambdaClient({'StatusCode': 200, 'Payload': json.dumps(OK).encode()})
    monkeypatch.setattr(proxy, 'lambda_client', client)
    assert proxy._invoke_lambda('GetAllItems', {'a': 1}) == OK
    assert client.calls == [{'FunctionName': 'GetAllItems', 'Payload': '{"a": 1}'}]
    monkeypatch.setattr(proxy, 'lambda_client', _LambdaClient(
        {'StatusCode': 200, 'FunctionError': 'Unhandled', 'Payload': b'{"errorMessage": "x"}'}))
    with pytest.raises(Exception):
        proxy._invoke_lambda('GetAllItems', {})


def test_function_error_maps_to_502(invoke_proxy, monkeypatch):
    monkeypatch.setattr(invoke_proxy, 'lambda_client', _LambdaClient(
        {'StatusCode': 200, 'FunctionError': 'Unhandled', 'Payload': b'{"errorMessage": "x"}'}))
    assert invoke_proxy._invoke({}, '/items', 'POST', user_id='u@x.co', rid='r1')['statusCode'] == 502


@pytest.mark.parametrize('mode,via', [('invoke', 'lambda'), ('', 'http')])
def test_proxy_mode_picks_invoke_or_http(proxy, monkeypatch, mode, via):
    monkeypatch.setattr(proxy, 'PROXY_MODE', mode)
    fn, up = _Lambda(OK), _Upstream(lambda req: _Ok())
    monkeypatch.setattr(proxy, '_invoke_lambda', fn)
    monkeypatch.setattr(proxy.urllib.request, 'urlopen', up)
    event = {'httpMethod': 'GET', 'pathParameters': {'proxy': 'items'},
             'headers': {'x-session-token': jwt_for('s', 'u@x.co')}}
    assert proxy.lambda_handler(event, None)['statusCode'] == 200
    assert (len(fn.calls), len(up.requests)) == ((1, 0) if via == 'lambda' else (0, 1))


# ── JWT secret from SSM (JWT_SECRET_PARAM) ────────────────────────────────────
class _Ssm:
    def __init__(self, value=None):
        self.value, self.calls = value, []

    def get_parameter(self, **kw):
        self.calls.append(kw)
        if self.value is None:
            raise RuntimeError('AccessDenied')
        return {'Parameter': {'Value': self.value}}


def _import_with_ssm(monkeypatch, ssm, param):
    import boto3
    real = boto3.client
    monkeypatch.setattr(boto3, 'client', lambda svc, *a, **kw: ssm if svc == 'ssm' else real(svc, *a, **kw))
    if param:
        monkeypatch.setenv('JWT_SECRET_PARAM', param)
    else:
        monkeypatch.delenv('JWT_SECRET_PARAM', raising=False)
    sys.modules.pop('Proxy', None)
    return importlib.import_module('Proxy')


def test_jwt_secret_read_from_ssm_when_param_set(proxy, monkeypatch):
    ssm = _Ssm('from-ssm')
    assert _import_with_ssm(monkeypatch, ssm, '/panindo/jwt')._JWT_SECRET == b'from-ssm'
    assert ssm.calls == [{'Name': '/panindo/jwt', 'WithDecryption': True}]


@pytest.mark.parametrize('param', ['/panindo/jwt', ''])
def test_jwt_secret_falls_back_to_env_on_failure_or_no_param(proxy, monkeypatch, param):
    ssm = _Ssm(None)
    assert _import_with_ssm(monkeypatch, ssm, param)._JWT_SECRET == b's'
    assert len(ssm.calls) == (1 if param else 0)


def test_invoke_mode_loads_without_legacy_http_env(monkeypatch):
    # Live rollout removes API_ENDPOINT/API_KEY once PROXY_MODE=invoke; Proxy must still cold-start.
    for name in ('API_ENDPOINT', 'API_KEY', 'API_KEY_SECRET'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('PROXY_MODE', 'invoke')
    monkeypatch.setenv('JWT_SECRET', 's')
    monkeypatch.setenv('LOG_STDOUT', '0')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.syspath_prepend(LAMBDA_DIR)
    for name in ('_logging', '_org', 'Proxy'):
        sys.modules.pop(name, None)
    assert importlib.import_module('Proxy').PROXY_MODE == 'invoke'
