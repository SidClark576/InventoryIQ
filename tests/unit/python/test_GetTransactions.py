"""GetTransactions: `since` returns org rows on/after the date, uncapped; no `since` keeps the 200 cap."""
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
            AttributeDefinitions=[{'AttributeName': n, 'AttributeType': 'S'} for n in ('transactionID', 'orgID', 'userID')],
            GlobalSecondaryIndexes=[_gsi('orgID'), _gsi('userID')],
            BillingMode='PAY_PER_REQUEST')
        members = ddb.create_table(
            TableName='OrgMembers',
            KeySchema=[{'AttributeName': 'orgID', 'KeyType': 'HASH'}, {'AttributeName': 'userID', 'KeyType': 'RANGE'}],
            AttributeDefinitions=[{'AttributeName': n, 'AttributeType': 'S'} for n in ('orgID', 'userID')],
            BillingMode='PAY_PER_REQUEST')
        members.put_item(Item={'orgID': ORG, 'userID': USER, 'role': 'viewer', 'status': 'active'})
        yield tx


def _put(tx, rows):
    with tx.batch_writer() as batch:
        for i, (org, created) in enumerate(rows):
            batch.put_item(Item={'transactionID': f't{i}', 'orgID': org, 'userID': USER, 'createdAt': created})


def _call(query):
    import GetTransactions
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
    assert len(json.loads(res['body'])) == 200


def test_bad_since_is_400(tables):
    assert _call({'since': 'yesterday'})['statusCode'] == 400


def test_out_of_range_since_is_400(tables):
    assert _call({'since': '0001-01-01T00:00:00+05:00'})['statusCode'] == 400
