"""The old Netlify site only redirects to app.panindo.app (job 014).

Netlify applies a `_redirects` file in the publish dir before netlify.toml, so the publish dir must not
hold one: frontend/public's Pages rewrites (`/accept.html / 200`) would shadow the 301 and 404 old links."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_netlify_publish_dir_has_no_redirects_file():
    conf = tomllib.loads((ROOT / 'netlify.toml').read_text())
    publish = ROOT / conf['build']['publish']
    assert publish.is_dir()
    assert not (publish / '_redirects').exists()
    assert conf['redirects'] == [{'from': '/*', 'to': 'https://app.panindo.app/:splat', 'status': 301, 'force': True}]
