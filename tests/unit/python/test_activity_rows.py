"""AC3: delete, restore and category delete each write an activity row (actor + orgID) and bump version/updatedAt."""
from datetime import datetime, timezone

HEADERS = {'x-iq-user': 'a@b.co', 'x-iq-org': 'o1'}
ITEM = {'itemID': 'i1', 'userID': 'owner@b.co', 'orgID': 'o1', 'name': 'Rice', 'quantity': 5,
        'version': 3, 'category': 'Snacks', 'updatedAt': 'old'}


def _rows(ddb):
    item = ddb.Table('InventoryIQ').get_item(Key={'itemID': 'i1'})['Item']
    return item, ddb.Table('InventoryTransactions').scan()['Items']


def _assert_logged(item, txs, change_type, notes):
    assert item['version'] == 4 and item['updatedAt'] != 'old'
    assert len(txs) == 1
    tx = txs[0]
    assert (tx['userID'], tx['orgID'], tx['changeType'], tx['itemID']) == ('a@b.co', 'o1', change_type, 'i1')
    assert notes in tx['notes']
    return tx


def test_delete_logs_actor_and_bumps_version(load, ddb):
    ddb.Table('InventoryIQ').put_item(Item=ITEM)
    res = load('DeleteItem').lambda_handler({'pathParameters': {'itemID': 'i1'}, 'headers': HEADERS}, None)
    assert res['statusCode'] == 200
    item, txs = _rows(ddb)
    assert item['deletedAt']
    tx = _assert_logged(item, txs, 'delete', 'soft-deleted')
    assert (tx['quantityBefore'], tx['quantityAfter'], tx['quantityDelta']) == (5, 0, -5)


def test_restore_logs_actor_and_bumps_version(load, ddb):
    deleted = datetime.now(timezone.utc).isoformat()
    ddb.Table('InventoryIQ').put_item(Item={**ITEM, 'deletedAt': deleted, 'deletedBy': 'x'})
    res = load('RestoreItem').lambda_handler({'pathParameters': {'itemID': 'i1'}, 'headers': HEADERS}, None)
    assert res['statusCode'] == 200
    item, txs = _rows(ddb)
    assert 'deletedAt' not in item
    tx = _assert_logged(item, txs, 'update', 'Item restored')
    assert (tx['quantityBefore'], tx['quantityAfter'], tx['quantityDelta']) == (5, 5, 0)


def test_category_delete_logs_each_move(load, ddb):
    ddb.Table('InventoryIQ').put_item(Item=ITEM)
    res = load('DeleteCategory').lambda_handler(
        {'httpMethod': 'DELETE', 'pathParameters': {'categoryName': 'Snacks'}, 'headers': HEADERS}, None)
    assert res['statusCode'] == 200 and res['headers']['Access-Control-Allow-Methods'] == 'OPTIONS,DELETE'
    item, txs = _rows(ddb)
    assert item['category'] == 'Uncategorized'
    tx = _assert_logged(item, txs, 'update', 'Category "Snacks" deleted; moved to Uncategorized')
    assert tx['quantityDelta'] == 0
