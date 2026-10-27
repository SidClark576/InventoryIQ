"""AC1: every Lambda's CORS default is one shared list that admits the app origins."""
import os
import re
import sys

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda'))
APP_ORIGINS = {'capacitor://localhost', 'https://localhost'}


def _split(value):
    return {o.strip() for o in value.split(',') if o.strip()}


def test_cors_defaults_match_and_admit_app_origins(monkeypatch):
    monkeypatch.delenv('CORS_ORIGIN', raising=False)
    monkeypatch.setenv('API_ENDPOINT', 'http://example.invalid')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.syspath_prepend(LAMBDA_DIR)
    for name in ('_logging', 'Proxy'):
        sys.modules.pop(name, None)
    import _logging
    import Proxy

    shared = _split(_logging.DEFAULT_CORS_ORIGINS)
    assert APP_ORIGINS <= shared
    assert _logging._CORS_ORIGINS == shared
    assert Proxy._CORS_ORIGINS == shared

    with open(os.path.join(LAMBDA_DIR, 'Authentication.mjs'), encoding='utf-8') as f:
        match = re.search(r"process\.env\.CORS_ORIGIN \|\| '([^']+)'", f.read())
    assert match, 'Authentication.mjs CORS default not found'
    assert _split(match.group(1)) == shared
