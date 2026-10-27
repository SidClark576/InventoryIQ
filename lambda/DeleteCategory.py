import os
import uuid
from datetime import datetime, timezone
import boto3
from boto3.dynamodb.types import TypeSerializer
import time as _time
import _logging
import _org

FUNCTION_NAME = 'DeleteCategory'

TABLE    = os.environ.get('DYNAMODB_TABLE', 'InventoryIQ')
TX_TABLE = os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions')

dynamodb   = boto3.resource('dynamodb')
table      = dynamodb.Table(TABLE)
ddb_client = boto3.client('dynamodb')
serializer = TypeSerializer()


def _resp(status, body):
    return _logging.response(status, body, methods='OPTIONS,DELETE')


def lambda_handler(event, context):
    t0 = _time.time()
    res = _handle(event, context)
    _logging.log_json(
        event=event,
        function=FUNCTION_NAME,
        latency_ms=(_time.time() - t0) * 1000,
        status=res.get('statusCode'),
        is_error=res.get('statusCode', 200) >= 500,
    )
    return res


def _handle(event, _context):
    """
    Deletes a category by reassigning all items in that category to "Uncategorized".

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Parse request body and extract userID and categoryName
    3. Prevent deletion of "Uncategorized" category (system requirement)
    4. Scan for all items with matching category and userID
    5. Per item, one transaction: category -> "Uncategorized", version + updatedAt bump, activity row
    6. Return count of items updated

    Request Body:
    - userID: Required. User email who owns the items
    - categoryName: Required. Category name to delete

    Response: {'itemsUpdated': N} where N is number of items reassigned

    Design Note: "Uncategorized" is not actually deleted, items are reassigned to it.
    This prevents orphaned items and ensures no data loss.
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return _resp(200, {})

    headers = event.get('headers') or {}
    ctx, err = _org.require_member(headers, minimum='editor')
    if err:
        return err
    category_name = (event.get('pathParameters') or {}).get('categoryName', '')
    if not category_name:
        return _resp(400, {'error': 'categoryName required'})

    # Prevent deletion of the "Uncategorized" category
    # This is a system category that must always exist as a fallback
    if category_name.lower() == 'uncategorized':
        return _resp(400, {'error': 'Cannot delete Uncategorized'})

    try:
        items = [
            i for i in _org.list_scoped_items(table, ctx['org_id'], ctx['user_id'])
            if i.get('category') == category_name
        ]
        # One transaction per item: move to Uncategorized + bump version + activity row (B2, B5)
        for item in items:
            _move(item, category_name, ctx)
    except Exception as e:
        return _logging.server_error(e, event, _logging.cors_headers('OPTIONS,DELETE'))
    return _resp(200, {'itemsUpdated': len(items)})


def _move(item, category_name, ctx):
    timestamp = datetime.now(timezone.utc).isoformat()
    qty = int(item.get('quantity', 0))
    tx_item = {
        'transactionID' : str(uuid.uuid4()),
        'itemID'        : item['itemID'],
        'itemName'      : item.get('name', ''),
        'userID'        : ctx['user_id'],
        'changeType'    : 'update',
        'quantityBefore': qty,
        'quantityAfter' : qty,
        'quantityDelta' : 0,
        'notes'         : f'Category "{category_name}" deleted; moved to Uncategorized',
        'createdAt'     : timestamp,
    }
    if ctx['org_id']:
        tx_item['orgID'] = ctx['org_id']
    ddb_client.transact_write_items(TransactItems=[
        {'Update': {
            'TableName'                : TABLE,
            'Key'                      : {'itemID': {'S': item['itemID']}},
            'UpdateExpression'         : 'SET category = :cat, updatedAt = :ts ADD #ver :one',
            'ConditionExpression'      : 'attribute_exists(itemID)',  # never recreate a purged item
            'ExpressionAttributeNames' : {'#ver': 'version'},
            'ExpressionAttributeValues': {':cat': {'S': 'Uncategorized'}, ':ts': {'S': timestamp}, ':one': {'N': '1'}},
        }},
        {'Put': {'TableName': TX_TABLE, 'Item': {k: serializer.serialize(v) for k, v in tx_item.items()}}},
    ])
