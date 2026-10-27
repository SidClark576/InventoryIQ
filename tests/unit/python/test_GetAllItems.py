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
        dynamodb.create_table(
            TableName='InventoryIQ',
            KeySchema=[{'AttributeName': 'itemID', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'itemID', 'AttributeType': 'S'},
                {'AttributeName': 'userID', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'userID-index',
                    'KeySchema': [{'AttributeName': 'userID', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        yield dynamodb

def test_get_all_items_success(dynamodb_setup):
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda')))
    import GetAllItems
    
    # Add a mock item
    dynamodb_setup.put_item(
        TableName='InventoryIQ',
        Item={
            'itemID': {'S': '123'},
            'userID': {'S': 'test@example.com'},
            'name': {'S': 'Test Product'},
            'quantity': {'N': '10'},
            'price': {'N': '9.99'}
        }
    )
    
    event = {
        'queryStringParameters': {
            'userID': 'test@example.com'
        }
    }
    
    response = GetAllItems.lambda_handler(event, {})
    assert response['statusCode'] == 200
    
    body = json.loads(response['body'])
    assert 'items' in body
    assert len(body['items']) == 1
    assert body['items'][0]['name'] == 'Test Product'
    assert body['items'][0]['price'] == 9.99

def test_get_all_items_no_user(dynamodb_setup):
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda')))
    import GetAllItems
    
    event = {
        'queryStringParameters': {}
    }
    
    response = GetAllItems.lambda_handler(event, {})
    # According to GetAllItems.py, it returns 200 with empty items when userID is missing
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['items'] == []


def test_get_all_items_returns_json_integers(load, ddb):
    ddb.Table('InventoryIQ').put_item(Item={'itemID': 'i1', 'userID': 'a@b.co', 'name': 'Rice',
                                            'quantity': 10, 'version': 2, 'lowStockThreshold': 3,
                                            'price': __import__('decimal').Decimal('9.99')})
    res = load('GetAllItems').lambda_handler({'headers': {'x-iq-user': 'a@b.co'}}, {})
    assert res['statusCode'] == 200
    item = json.loads(res['body'])['items'][0]
    assert [type(item[k]) for k in ('quantity', 'version', 'lowStockThreshold')] == [int] * 3
    assert item['price'] == 9.99
