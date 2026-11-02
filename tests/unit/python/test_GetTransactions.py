"""GetTransactions: `since` returns org rows on/after the date, uncapped; no `since` keeps the 200 cap;
`limit`/`cursor` page the orgID-createdAt-index; never a scan, and a missing GSI falls back to orgID-index."""
import base64
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda')))

ORG = 'org-1'
USER = 'owner@example.com'
HEADERS = {'x-iq-user': USER, 'x-iq-org': ORG}


def _gsi(name):
    return {'IndexName': f'{name}-index', 'KeySchema': [{'AttributeName': name, 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'}}


@pytest.fixture
def tables(monkeypatch):
    for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SECURITY_TOKEN', 'AWS_SESSION_TOKEN'):
        monkeypatch.setenv(key, 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    with mock_aws():
        ddb = boto3.resource('dynamodb', region_name='us-east-1')
        tx = ddb.create_table(
            TableName='InventoryTransactions',
            KeySchema=[{'AttributeName': 'transactionID', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': n, 'AttributeType': 'S'}
                                  for n in ('transactionID', 'orgID', 'userID', 'createdAt')],
            GlobalSecondaryIndexes=[_gsi('orgID'), _gsi('userID'), {
                'IndexName': 'orgID-createdAt-index', 'Projection': {'ProjectionType': 'ALL'},
                'KeySchema': [{'AttributeName': 'orgID', 'KeyType': 'HASH'}, {'AttributeName': 'createdAt', 'KeyType': 'RANGE'}]}],
            BillingMode='PAY_PER_REQUEST')
        members = ddb.create_table(
            TableName='OrgMembers',
            KeySchema=[{'AttributeName': 'orgID', 'KeyType': 'HASH'}, {'AttributeName': 'userID', 'KeyType': 'RANGE'}],
            AttributeDefinitions=[{'AttributeName': n, 'AttributeType': 'S'} for n in ('orgID', 'userID')],
            BillingMode='PAY_PER_REQUEST')
        members.put_item(Item={'orgID': ORG, 'userID': USER, 'role': 'viewer', 'status': 'active'})
        yield tx


def _no_scan(**kw):
    raise AssertionError('GetTransactions must never scan')


def _put(tx, rows):
    with tx.batch_writer() as batch:
        for i, (org, created) in enumerate(rows):
            batch.put_item(Item={'transactionID': f't{i}', 'orgID': org, 'userID': USER, 'createdAt': created})


def _call(query):
    import GetTransactions
    GetTransactions.table.scan = _no_scan
    return GetTransactions.lambda_handler({'httpMethod': 'GET', 'headers': HEADERS, 'queryStringParameters': query}, None)


def test_since_returns_org_rows_on_or_after_the_date_without_the_cap(tables):
    after = [(ORG, f'2026-10-{1 + i % 27:02d}T0{i % 10}:00:00.000001+00:00') for i in range(205)]
    _put(tables, after + [(ORG, '2026-09-30T15:59:59+00:00'), ('org-2', '2026-10-05T00:00:00+00:00'),
                          (ORG, '2026-09-30T16:00:00+00:00')])
    res = _call({'since': '2026-09-30T16:00:00.000Z'})
    assert res['statusCode'] == 200
    rows = json.loads(res['body'])
    assert len(rows) == 206
    assert all(r['orgID'] == ORG and r['createdAt'] >= '2026-09-30T16:00:00+00:00' for r in rows)


def test_without_since_keeps_the_200_cap(tables):
    _put(tables, [(ORG, f'2026-10-01T00:00:{i % 60:02d}.{i:06d}+00:00') for i in range(205)])
    res = _call(None)
    assert res['statusCode'] == 200
    rows = json.loads(res['body'])
    assert len(rows) == 200
    assert [r['createdAt'] for r in rows] == sorted((r['createdAt'] for r in rows), reverse=True)
    assert rows[0]['createdAt'] == '2026-10-01T00:00:59.000179+00:00'


def test_no_params_is_only_the_callers_org(tables):
    _put(tables, [(ORG, '2026-10-01T00:00:00+00:00'), ('org-2', '2026-10-02T00:00:00+00:00')])
    assert [r['orgID'] for r in json.loads(_call(None)['body'])] == [ORG]


def test_since_is_a_key_condition_not_a_filter(tables, monkeypatch):
    import GetTransactions
    seen = []
    real = GetTransactions.table.query
    monkeypatch.setattr(GetTransactions.table, 'query', lambda **kw: seen.append(kw) or real(**kw))
    assert _call({'since': '2026-10-01'})['statusCode'] == 200
    assert seen and all('FilterExpression' not in kw and kw['IndexName'] == 'orgID-createdAt-index' for kw in seen)
    assert 'Limit' not in seen[0]


def test_limit_and_cursor_page_without_overlap(tables):
    _put(tables, [(ORG, f'2026-10-0{d}T00:00:00+00:00') for d in (1, 2, 3)] + [('org-2', '2026-10-04T00:00:00+00:00')])
    first = json.loads(_call({'limit': '2'})['body'])
    assert [r['createdAt'][:10] for r in first['items']] == ['2026-10-03', '2026-10-02']
    second = json.loads(_call({'limit': '2', 'cursor': first['nextCursor']})['body'])
    assert [r['createdAt'][:10] for r in second['items']] == ['2026-10-01']
    assert 'nextCursor' not in second


def test_exactly_full_last_page_has_no_cursor(tables, monkeypatch):
    import GetTransactions
    real = GetTransactions.table.query

    def dynamo_like(**kw):  # real DynamoDB returns LastEvaluatedKey whenever Limit is hit, even at the end; moto doesn't
        res = real(**kw)
        if kw.get('Limit') == len(res['Items']) and res['Items']:
            res.setdefault('LastEvaluatedKey', {k: res['Items'][-1][k] for k in ('transactionID', 'orgID', 'createdAt')})
        return res
    monkeypatch.setattr(GetTransactions.table, 'query', dynamo_like)
    _put(tables, [(ORG, f'2026-10-0{d}T00:00:00+00:00') for d in (1, 2, 3, 4)])
    first = json.loads(_call({'limit': '2'})['body'])
    second = json.loads(_call({'limit': '2', 'cursor': first['nextCursor']})['body'])
    assert [r['createdAt'][:10] for r in second['items']] == ['2026-10-02', '2026-10-01']
    assert 'nextCursor' not in second


def test_other_query_errors_are_500_not_a_fallback(tables, monkeypatch):
    from botocore.exceptions import ClientError
    import GetTransactions

    def denied(**kw):
        raise ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'no'}}, 'Query')
    monkeypatch.setattr(GetTransactions.table, 'query', denied)
    monkeypatch.setattr(GetTransactions._org, 'list_scoped_items', lambda *a: pytest.fail('fell back'))
    assert _call(None)['statusCode'] == 500


@pytest.mark.parametrize('query', [{'limit': '0'}, {'limit': '201'}, {'limit': 'two'}, {'cursor': '!!'},
                                   {'cursor': base64.urlsafe_b64encode(b'[1]').decode()},
                                   {'cursor': base64.urlsafe_b64encode(json.dumps(
                                       {'orgID': 'org-2', 'transactionID': 't0', 'createdAt': 'x'}).encode()).decode()}])
def test_bad_limit_or_cursor_is_400(tables, query):
    assert _call(query)['statusCode'] == 400


def test_without_the_new_gsi_falls_back_to_org_index(load, ddb):
    tx = ddb.Table('InventoryTransactions')
    for i in range(205):
        tx.put_item(Item={'transactionID': f't{i}', 'orgID': 'o1', 'userID': 'a@b.co',
                          'createdAt': f'2026-10-01T00:00:{i % 60:02d}.{i:06d}+00:00'})
    tx.put_item(Item={'transactionID': 'x', 'orgID': 'o2', 'userID': 'z@b.co', 'createdAt': '2027-01-01T00:00:00+00:00'})
    mod = load('GetTransactions')
    mod.table.scan = _no_scan

    def call(query=None):
        return json.loads(mod.lambda_handler({'headers': {'x-iq-user': 'a@b.co', 'x-iq-org': 'o1'},
                                              'queryStringParameters': query}, {})['body'])
    rows = call()
    assert len(rows) == 200 and {r['orgID'] for r in rows} == {'o1'}
    assert [r['createdAt'] for r in rows] == sorted((r['createdAt'] for r in rows), reverse=True)
    first = call({'limit': '150'})
    second = call({'limit': '150', 'cursor': first['nextCursor']})
    ids = [r['transactionID'] for r in first['items'] + second['items']]
    assert len(ids) == len(set(ids)) == 205 and 'nextCursor' not in second


def test_bad_since_is_400(tables):
    assert _call({'since': 'yesterday'})['statusCode'] == 400


def test_out_of_range_since_is_400(tables):
    assert _call({'since': '0001-01-01T00:00:00+05:00'})['statusCode'] == 400


def test_transactions_return_json_integers(load, ddb):
    ddb.Table('InventoryTransactions').put_item(Item={
        'transactionID': 't1', 'orgID': 'o1', 'userID': 'a@b.co', 'createdAt': '2026-01-01T00:00:00+00:00',
        'quantityBefore': 5, 'quantityAfter': 3, 'quantityDelta': -2})
    res = load('GetTransactions').lambda_handler({'headers': {"x-iq-user": "a@b.co", "x-iq-org": "o1"}}, {})
    assert res['statusCode'] == 200
    tx = json.loads(res['body'])[0]
    assert [type(tx[k]) for k in ('quantityBefore', 'quantityAfter', 'quantityDelta')] == [int] * 3
