import decimal
import json


def test_get_all_items_success(load, ddb):
    ddb.Table('InventoryIQ').put_item(Item={'itemID': '123', 'userID': 'test@example.com', 'name': 'Test Product',
                                            'quantity': 10, 'price': decimal.Decimal('9.99')})
    response = load('GetAllItems').lambda_handler({'headers': {'x-iq-user': 'test@example.com'}}, {})
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert len(body['items']) == 1
    assert body['items'][0]['name'] == 'Test Product'
    assert body['items'][0]['price'] == 9.99


def test_get_all_items_no_user(load, ddb):
    response = load('GetAllItems').lambda_handler({'headers': {}}, {})
    assert response['statusCode'] == 401
    assert json.loads(response['body']) == {'error': 'Unauthorized'}


def test_get_all_items_returns_json_integers(load, ddb):
    ddb.Table('InventoryIQ').put_item(Item={'itemID': 'i1', 'userID': 'a@b.co', 'name': 'Rice',
                                            'quantity': 10, 'version': 2, 'lowStockThreshold': 3,
                                            'price': __import__('decimal').Decimal('9.99')})
    res = load('GetAllItems').lambda_handler({'headers': {'x-iq-user': 'a@b.co'}}, {})
    assert res['statusCode'] == 200
    item = json.loads(res['body'])['items'][0]
    assert [type(item[k]) for k in ('quantity', 'version', 'lowStockThreshold')] == [int] * 3
    assert item['price'] == 9.99
