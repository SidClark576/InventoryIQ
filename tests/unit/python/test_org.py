"""AC2: a selected org with no OrgMembers table fails closed (403, no role)."""
import json
import os
import sys

from moto import mock_aws

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda'))


def test_require_member_without_members_table_is_403(monkeypatch):
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.syspath_prepend(LAMBDA_DIR)
    with mock_aws():
        sys.modules.pop('_org', None)
        import _org
        # Real path: moto raises ResourceNotFoundException → get_membership returns None
        assert _org.get_membership('org-1', 'a@b.co') is None
        ctx, err = _org.require_member({'x-iq-user': 'a@b.co', 'x-iq-org': 'org-1'})
    assert ctx is None
    assert err['statusCode'] == 403
    assert 'owner' not in json.dumps(err)
