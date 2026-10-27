import json
import os
import boto3
from boto3.dynamodb.conditions import Attr
from datetime import datetime, timezone
from decimal import Decimal
import time as _time
import _logging
import _org

FUNCTION_NAME = 'GetTransactions'

# Initialize DynamoDB with transactions table
# This table holds the audit log of all inventory changes
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))

# Standard CORS headers for GET requests
CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,GET'
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


def _since(event):
    """`since` query param as stored-format UTC ISO (createdAt is datetime.isoformat() +00:00), or None. Raises ValueError or OverflowError."""
    since = (event.get('queryStringParameters') or {}).get('since')
    if not since:
        return None
    dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def _handle(event, context):
    """
    Retrieves transaction history (audit log) for a specific user.

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Extract and validate userID from query parameters
    3. Scan InventoryTransactions table filtering by userID
    4. Handle pagination (DynamoDB returns up to 1MB per scan)
    5. Convert Decimal types to float for JSON
    6. Sort transactions by date (newest first)
    7. Return up to 200 most recent transactions

    Query Parameters:
    - since: Optional UTC ISO date. Only rows with createdAt >= since, and no 200 cap.

    Response: Array of transaction objects sorted newest-first, max 200 items unless `since` is given

    Transaction Types:
    - create: Item added to inventory
    - stock_in: Quantity increased (restocking)
    - stock_out: Quantity decreased (depletion)
    - update: Other fields changed (name, price, category, etc)
    - delete: Item removed from inventory
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    headers = event.get('headers') or {}
    ctx, err = _org.require_member(headers, minimum='viewer')
    if err:
        return err

    try:
        since = _since(event)
    except (ValueError, OverflowError):
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'since must be an ISO date'})}
    since_filt = Attr('createdAt').gte(since) if since else None

    try:
        try:
            items = _org.list_scoped_items(table, ctx['org_id'], ctx['user_id'], since_filt)
        except Exception:
            filt = Attr('orgID').eq(ctx['org_id']) if ctx['org_id'] else Attr('userID').eq(ctx['user_id'])
            if since_filt is not None:
                filt = filt & since_filt
            result = table.scan(FilterExpression=filt)
            items = result.get('Items', [])
            while 'LastEvaluatedKey' in result:
                result = table.scan(
                    ExclusiveStartKey=result['LastEvaluatedKey'],
                    FilterExpression=filt
                )
                items.extend(result.get('Items', []))

        # Convert Decimal types to float for JSON serialization
        # DynamoDB returns Decimal objects which JSON cannot serialize by default
        for item in items:
            for k, v in item.items():
                if isinstance(v, Decimal):
                    item[k] = float(v)

        # Sort by creation date, newest transactions first
        # This provides a reverse-chronological view of activity
        items.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

        # Up to 200 most recent for the activity feed; a `since` range (stock report) is returned whole
        return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(items if since else items[:200])}

    except Exception as e:
        return {'statusCode': 500, 'headers': CORS, 'body': json.dumps({'error': 'Internal Server Error'})}
