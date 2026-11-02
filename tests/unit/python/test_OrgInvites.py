"""OrgInvites: a new invite carries `ttl` (epoch seconds, = expiresAt) so DynamoDB TTL can drop it once expired."""
import json

from conftest import _table


def test_new_invite_ttl_equals_expires_at(load, ddb):
    ddb.Table('OrgMembers').put_item(Item={'orgID': 'o1', 'userID': 'boss@b.co', 'role': 'owner', 'status': 'active'})
    ddb.Table('OrgInvites').delete()
    _table(ddb, 'OrgInvites', 'inviteTokenHash', gsis=('orgID', 'email'))
    _table(ddb, 'Organizations', 'orgID')
    ddb.Table('Organizations').put_item(Item={'orgID': 'o1', 'seatCount': 1})
    res = load('OrgInvites').lambda_handler({
        'httpMethod': 'POST', 'path': '/orgs/o1/invites', 'pathParameters': {'id': 'o1'},
        'headers': {'x-iq-user': 'boss@b.co'}, 'body': json.dumps({'email': 'new@b.co'})}, None)
    assert res['statusCode'] == 201
    invite = ddb.Table('OrgInvites').scan()['Items'][0]
    assert invite['ttl'] == invite['expiresAt'] and invite['ttl'] > 0
