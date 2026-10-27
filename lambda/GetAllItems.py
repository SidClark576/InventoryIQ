import json
import boto3
import os
from boto3.dynamodb.conditions import Key, Attr
import time as _time
import _logging
import _org

FUNCTION_NAME = 'GetAllItems'

# Initialize DynamoDB resource and get the inventory table
# Table name is configurable via DYNAMODB_TABLE env var, defaults to 'InventoryIQ'
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

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


def _handle(event, context):
    """
    Retrieves all active (non-deleted) inventory items for a specific user.

    Sprint 3 change:
    - FilterExpression=Attr('deletedAt').not_exists() excludes soft-deleted items
      from both the initial query page and all paginated continuation pages

    Flow:
    1. Extract userID from query parameters
    2. Return empty list if userID is missing (user isolation requirement)
    3. Query userID-index GSI filtering by userID + excluding soft-deleted items
    4. Handle pagination (DynamoDB returns max 1MB per page)
    5. Convert Decimals to JSON numbers (integers stay integers)
    6. Return items array with count

    Query Parameters:
    - userID: Required. Email of the user to filter items by.
    - deleted: Optional. Pass "true" to return only soft-deleted items instead of active ones.

    Response: {'items': [...], 'count': N}
    """
    try:
        headers = event.get('headers') or {}
        ctx, err = _org.require_member(headers, minimum='viewer')
        if err:
            return err

        params = event.get('queryStringParameters') or {}
        show_deleted = params.get('deleted', '').lower() == 'true'
        filter_expr = Attr('deletedAt').exists() if show_deleted else Attr('deletedAt').not_exists()
        items = _org.list_scoped_items(table, ctx['org_id'], ctx['user_id'], filter_expr)

        items = [_logging.plain(item) for item in items]

        return _logging.response(200, {'items': items, 'count': len(items)})

    except Exception as e:
        _logging.capture_error(e, function=FUNCTION_NAME)
        return _logging.response(500, {'error': 'Internal Server Error'})
