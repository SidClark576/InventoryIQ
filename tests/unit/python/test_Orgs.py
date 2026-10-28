"""AC1/AC2: PUT /orgs/{id} saves store fields (owner only, onboardedAt once); /switch returns them."""
import json

import pytest

from conftest import _table

OWNER = {'x-iq-user': 'o@b.co'}
EDITOR = {'x-iq-user': 'a@b.co'}


@pytest.fixture
def orgs(load, ddb):
    _table(ddb, 'Organizations', 'orgID')
    ddb.Table('Organizations').put_item(Item={'orgID': 'o1', 'name': 'My Inventory', 'ownerUserID': 'o@b.co'})
    ddb.Table('OrgMembers').put_item(Item={'orgID': 'o1', 'userID': 'o@b.co', 'role': 'owner', 'status': 'active'})
    return load('Orgs')


def call(mod, method, headers, body=None, path='/orgs/o1'):
    res = mod.lambda_handler({'httpMethod': method, 'path': path, 'headers': headers,
                              'pathParameters': {'id': 'o1'},
                              'body': json.dumps(body) if body is not None else None}, None)
    return res['statusCode'], json.loads(res['body'])


def test_owner_put_saves_fields_and_stamps_onboarded_once(orgs, ddb):
    status, body = call(orgs, 'PUT', OWNER, {'name': ' SC3 Store ', 'storeType': 'sari-sari',
                                            'country': 'PH', 'currency': 'PHP'})
    assert status == 200
    assert body['name'] == 'SC3 Store' and body['currency'] == 'PHP' and body['onboardedAt']
    first = body['onboardedAt']
    status, body = call(orgs, 'PUT', OWNER, {'name': 'SC3 Sari-Sari'})
    assert status == 200 and body['onboardedAt'] == first
    row = ddb.Table('Organizations').get_item(Key={'orgID': 'o1'})['Item']
    assert row['name'] == 'SC3 Sari-Sari' and row['storeType'] == 'sari-sari' and row['onboardedAt'] == first


def test_editor_put_is_403(orgs):
    assert call(orgs, 'PUT', EDITOR, {'name': 'X'})[0] == 403


@pytest.mark.parametrize('body', [{'name': '  '}, {'name': 'X', 'storeType': 'casino'},
                                  {'name': 'X', 'country': 'ph'}, {'name': 'X', 'currency': 'PESO'},
                                  {'name': 'x' * 81}])
def test_bad_body_is_400(orgs, body):
    assert call(orgs, 'PUT', OWNER, body)[0] == 400


def test_switch_returns_store_fields(orgs):
    call(orgs, 'PUT', OWNER, {'name': 'SC3', 'storeType': 'grocery', 'country': 'PH', 'currency': 'PHP'})
    status, body = call(orgs, 'POST', OWNER, path='/orgs/o1/switch')
    assert status == 200
    assert {k: body[k] for k in ('role', 'name', 'storeType', 'country', 'currency')} == {
        'role': 'owner', 'name': 'SC3', 'storeType': 'grocery', 'country': 'PH', 'currency': 'PHP'}
    assert body['onboardedAt']
