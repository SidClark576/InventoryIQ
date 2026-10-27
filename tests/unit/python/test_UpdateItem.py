"""AC3: both 412 responses carry the current item and its version as ETag."""
import json
import os
import sys
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda'))
ROW = {'itemID': 'i1', 'userID': 'a@b.co', 'name': 'Rice', 'quantity': Decimal(5),
       'price': Decimal('9.5'), 'version': Decimal(3)}


@pytest.fixture
def update_item(monkeypatch):
    for k, v in {'AWS_DEFAULT_REGION': 'us-east-1', 'AWS_ACCESS_KEY_ID': 'testing',
                 'AWS_SECRET_ACCESS_KEY': 'testing', 'LOG_STDOUT': '0'}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.syspath_prepend(LAMBDA_DIR)
    with mock_aws():
        for name in ('_logging', '_org', 'UpdateItem'):
            sys.modules.pop(name, None)
        import UpdateItem
        for name, key in (('InventoryIQ', 'itemID'), ('InventoryTransactions', 'transactionID')):
            UpdateItem.dynamodb.create_table(
                TableName=name, KeySchema=[{'AttributeName': key, 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': key, 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST')
        UpdateItem.table.put_item(Item=ROW)
        yield UpdateItem


def _event(version):
    return {'pathParameters': {'itemID': 'i1'}, 'body': json.dumps({'quantity': 6}),
            'headers': {'x-iq-user': 'a@b.co', 'if-match': str(version)}}


def _assert_conflict(res):
    assert res['statusCode'] == 412
    assert res['headers']['ETag'] == '3'
    item = json.loads(res['body'])['item']
    assert item['version'] == 3 and item['quantity'] == 5 and item['price'] == 9.5


def test_stale_version_412_returns_current_item(update_item):
    _assert_conflict(update_item.lambda_handler(_event(2), None))


def test_concurrent_412_returns_current_item(update_item, monkeypatch):
    def lost_race(**kw):
        raise ClientError({'Error': {'Code': 'TransactionCanceledException', 'Message': 'x'}}, 'TransactWriteItems')
    monkeypatch.setattr(update_item.ddb_client, 'transact_write_items', lost_race)
    _assert_conflict(update_item.lambda_handler(_event(3), None))


def _code(res):
    return json.loads(res['body']).get('code')


@pytest.mark.parametrize('field,value', [('quantity', -1), ('price', 'abc'), ('lowStockThreshold', 1.5)])
def test_bad_number_is_400_with_field(update_item, field, value):
    event = {**_event(3), 'body': json.dumps({field: value})}
    res = update_item.lambda_handler(event, None)
    assert res['statusCode'] == 400 and _code(res) == 'INVALID_FIELD'
    assert json.loads(res['body'])['field'] == field
    assert update_item.table.get_item(Key={'itemID': 'i1'})['Item']['version'] == 3


def test_bad_json_is_400(update_item):
    res = update_item.lambda_handler({**_event(3), 'body': '{bad'}, None)
    assert res['statusCode'] == 400 and _code(res) == 'INVALID_JSON'


def test_deleted_item_is_410_and_not_written(update_item, monkeypatch):
    update_item.table.update_item(Key={'itemID': 'i1'}, UpdateExpression='SET deletedAt = :d',
                                  ExpressionAttributeValues={':d': '2026-01-01T00:00:00+00:00'})
    calls = []
    monkeypatch.setattr(update_item.ddb_client, 'transact_write_items', lambda **kw: calls.append(kw))
    res = update_item.lambda_handler(_event(3), None)
    assert res['statusCode'] == 410 and _code(res) == 'ITEM_DELETED' and calls == []


def test_valid_update_keeps_integers(update_item):
    event = {**_event(3), 'body': json.dumps({'quantity': 6, 'price': '12.25', 'name': 'Rice 5kg'})}
    res = update_item.lambda_handler(event, None)
    assert res['statusCode'] == 200
    item = json.loads(res['body'])['item']
    assert type(item['quantity']) is int and type(item['version']) is int and item['price'] == 12.25
    row = update_item.table.get_item(Key={'itemID': 'i1'})['Item']
    assert row['name'] == 'Rice 5kg' and row['price'] == Decimal('12.25') and row['version'] == 4
