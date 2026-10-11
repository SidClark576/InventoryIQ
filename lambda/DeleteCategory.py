import json
import os
import boto3
from boto3.dynamodb.conditions import Attr
import time as _time
import _logging
import _org

FUNCTION_NAME = 'DeleteCategory'

# Initialize DynamoDB with inventory table
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

# Standard CORS headers for POST requests
CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
}

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
    5. Update each item: set category to "Uncategorized"
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
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    headers = event.get('headers') or {}
    ctx, err = _org.require_member(headers, minimum='editor')
    if err:
        return err
    category_name = (event.get('pathParameters') or {}).get('categoryName', '')
    if not category_name:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'categoryName required'})}

    # Prevent deletion of the "Uncategorized" category
    # This is a system category that must always exist as a fallback
    if category_name.lower() == 'uncategorized':
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Cannot delete Uncategorized'})}

    items = [
        i for i in _org.list_scoped_items(table, ctx['org_id'], ctx['user_id'])
        if i.get('category') == category_name
    ]

    # Update each item: reassign category to "Uncategorized"
    # This prevents orphaned items and ensures smooth category deletion
    items_updated = 0
    for item in items:
        table.update_item(
            Key={'itemID': item['itemID']},
            UpdateExpression='SET category = :cat',
            ExpressionAttributeValues={':cat': 'Uncategorized'}
        )
        items_updated += 1

    # Return the count of items updated
    # This informs the frontend how many items were reassigned
    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps({'itemsUpdated': items_updated})}
