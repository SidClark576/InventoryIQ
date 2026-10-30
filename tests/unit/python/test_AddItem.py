import pytest
import os
import json
import boto3
from moto import mock_aws

@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

@pytest.fixture
def dynamodb_setup(aws_credentials):
    with mock_aws():
        dynamodb = boto3.client('dynamodb', region_name='us-east-1')
        
        # Create Tables required by AddItem.py
        dynamodb.create_table(
            TableName='InventoryIQ',
            KeySchema=[{'AttributeName': 'itemID', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'itemID', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        dynamodb.create_table(
            TableName='InventoryTransactions',
            KeySchema=[{'AttributeName': 'transactionID', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'transactionID', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        dynamodb.create_table(
            TableName='IdempotencyKeys',
            KeySchema=[{'AttributeName': 'key', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'key', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        yield dynamodb

def test_add_item_success(dynamodb_setup, monkeypatch):
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda')))
    import AddItem
    
    # Mocking internal _time module for deterministic output if needed
    
    event = {
        'body': json.dumps({
            'name': 'Test Item',
            'quantity': 10,
            'price': 9.99
        }),
        'headers': {
            'x-iq-user': 'test@example.com',
            'idempotency-key': 'test-idem-key-123'
        }
    }
    
    response = AddItem.lambda_handler(event, {})
    
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    assert body['message'] == 'Item added successfully'
    assert body['item']['name'] == 'Test Item'
    assert body['item']['userID'] == 'test@example.com'
    assert body['item']['version'] == 1

def test_add_item_missing_name(dynamodb_setup):
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda')))
    import AddItem
    
    event = {
        'body': json.dumps({
            'quantity': 10
        }),
        'headers': {}
    }
    
    response = AddItem.lambda_handler(event, {})
    assert response['statusCode'] == 400
    assert 'error' in json.loads(response['body'])

def test_add_item_idempotency_replay(dynamodb_setup):
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda')))
    import AddItem
    
    event = {
        'body': json.dumps({
            'name': 'Test Item Idem',
            'quantity': 5
        }),
        'headers': {
            'x-iq-user': 'test@example.com',
            'idempotency-key': 'idem-replay-key'
        }
    }
    
    # First call
    response1 = AddItem.lambda_handler(event, {})
    assert response1['statusCode'] == 201
    
    # Second call should replay
    response2 = AddItem.lambda_handler(event, {})
    assert response2['statusCode'] == 200 # Replay returns 200
    assert json.loads(response2['body']) == json.loads(response1['body'])


@pytest.mark.parametrize('field,value', [('quantity', -3), ('price', 'free'), ('lowStockThreshold', 'x')])
def test_add_item_bad_number_is_400(load, field, value):
    _load_idem_table()
    res = load('AddItem').lambda_handler(
        {'body': json.dumps({'name': 'Rice', field: value}), 'headers': {'x-iq-user': 'a@b.co'}}, {})
    body = json.loads(res['body'])
    assert res['statusCode'] == 400 and body['code'] == 'INVALID_FIELD' and body['field'] == field


def test_add_item_bad_json_is_400(load):
    res = load('AddItem').lambda_handler({'body': 'nope', 'headers': {'x-iq-user': 'a@b.co'}}, {})
    assert res['statusCode'] == 400 and json.loads(res['body'])['code'] == 'INVALID_JSON'


def test_add_item_returns_integers(load):
    _load_idem_table()
    res = load('AddItem').lambda_handler(
        {'body': json.dumps({'name': 'Rice', 'quantity': 4, 'price': 9.5}), 'headers': {'x-iq-user': 'a@b.co'}}, {})
    assert res['statusCode'] == 201
    item = json.loads(res['body'])['item']
    assert type(item['quantity']) is int and type(item['lowStockThreshold']) is int and item['price'] == 9.5


def _load_idem_table():
    boto3.client('dynamodb').create_table(
        TableName='IdempotencyKeys', KeySchema=[{'AttributeName': 'key', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'key', 'AttributeType': 'S'}], BillingMode='PAY_PER_REQUEST')


def _add(body):
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda')))
    import AddItem
    return AddItem.lambda_handler({'body': json.dumps({'name': 'Milk', **body}),
                                   'headers': {'x-iq-user': 'test@example.com'}}, {})


@pytest.mark.parametrize('body,stored', [({'expiresAt': '2026-11-15'}, '2026-11-15'), ({}, '')])
def test_add_item_stores_expires_at(dynamodb_setup, body, stored):
    res = _add(body)
    assert res['statusCode'] == 201
    assert json.loads(res['body'])['item']['expiresAt'] == stored


def test_add_item_bad_expires_at_is_400(dynamodb_setup):
    res = _add({'expiresAt': '15/11/2026'})
    assert res['statusCode'] == 400
    assert json.loads(res['body'])['field'] == 'expiresAt'
