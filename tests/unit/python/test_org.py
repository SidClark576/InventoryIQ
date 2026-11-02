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


def test_pending_invite_expires_at_is_iso(load, ddb):
    ddb.Table('OrgInvites').put_item(Item={'inviteTokenHash': 'h', 'orgID': 'o1', 'email': 'c@d.co',
                                           'role': 'viewer', 'status': 'pending', 'expiresAt': 1798761600})
    res = load('OrgMembers')._list('o1')
    assert json.loads(res['body'])['pendingInvites'][0]['expiresAt'] == '2027-01-01T00:00:00+00:00'


def test_list_user_orgs_batches_gets_and_keeps_rows(load, ddb, monkeypatch):
    from conftest import _table
    _table(ddb, 'Organizations', 'orgID')
    orgs, members = ddb.Table('Organizations'), ddb.Table('OrgMembers')
    ddb.meta.client.update_table(  # conftest's OrgMembers has no userID-index
        TableName='OrgMembers', AttributeDefinitions=[{'AttributeName': 'userID', 'AttributeType': 'S'}],
        GlobalSecondaryIndexUpdates=[{'Create': {'IndexName': 'userID-index', 'Projection': {'ProjectionType': 'ALL'},
                                                 'KeySchema': [{'AttributeName': 'userID', 'KeyType': 'HASH'}]}}])
    for i in range(130):
        orgs.put_item(Item={'orgID': f'p{i:03d}', 'name': f'Org {i}', 'memberCount': 2,
                            **({'deletedAt': 'x'} if i == 5 else {})})
        members.put_item(Item={'orgID': f'p{i:03d}', 'userID': 'm@b.co', 'role': 'editor',
                               'status': 'removed' if i == 7 else 'active'})
    mod = load('_org')
    calls = []
    real = mod._ddb.batch_get_item
    monkeypatch.setattr(mod._ddb, 'batch_get_item', lambda **kw: calls.append(kw) or real(**kw))
    monkeypatch.setattr(mod._orgs, 'get_item', lambda **kw: (_ for _ in ()).throw(AssertionError('get_item')))
    rows = mod.list_user_orgs('m@b.co')
    assert len(calls) == 2 and [len(c['RequestItems']['Organizations']['Keys']) for c in calls] == [100, 29]
    assert len(rows) == 128 and {r['orgID'] for r in rows}.isdisjoint({'p005', 'p007'})
    assert rows[0] == {'orgID': 'p000', 'name': 'Org 0', 'role': 'editor', 'memberCount': 2}
