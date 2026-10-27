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
