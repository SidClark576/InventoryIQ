import json
import os
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# Initialize DynamoDB with transactions table
# This table holds the audit log of all inventory changes
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TRANSACTIONS_TABLE', 'InventoryTransactions'))
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Retrieves transaction history (audit log) for a specific user.

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Extract verified userID from X-Verified-UserID header (injected by Proxy.py)
    3. Return 401 if userID is missing (authentication requirement)
    4. Query GSI (userID-index) filtering by userID, sorted by createdAt (newest first)
    5. Handle pagination (DynamoDB returns up to 1MB per query)
    6. Convert Decimal types to float for JSON
    7. Return up to 200 most recent transactions

    Auth: X-Verified-UserID header (verified by Proxy.py after JWT validation)

    Response: Array of transaction objects sorted newest-first, max 200 items

    Transaction Types:
    - create: Item added to inventory
    - stock_in: Quantity increased (restocking)
    - stock_out: Quantity decreased (depletion)
    - update: Other fields changed (name, price, category, etc)
    - delete: Item removed from inventory

    Performance: O(user transactions) using GSI, not O(total transactions) using scan.
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return response(200, '')

    # Extract verified userID from header (injected by Proxy.py after JWT validation)
    user_id = event.get('headers', {}).get('x-verified-userid', '').strip()
    if not user_id:
        return response(401, {'error': 'Missing or invalid authorization'})

    # Query GSI (userID-index) instead of full table scan
    # GSI structure: partition key = userID, sort key = createdAt
    # ScanIndexForward=False returns newest-first (reverse chronological)
    result = table.query(
        IndexName='userID-index',
        KeyConditionExpression=Key('userID').eq(user_id),
        ScanIndexForward=False  # Sort by createdAt descending (newest first)
    )
    items = result.get('Items', [])

    # Pagination loop: continue querying if more results exist (LastEvaluatedKey present)
    while 'LastEvaluatedKey' in result:
        result = table.query(
            IndexName='userID-index',
            KeyConditionExpression=Key('userID').eq(user_id),
            ScanIndexForward=False,
            ExclusiveStartKey=result['LastEvaluatedKey']
        )
        items.extend(result.get('Items', []))

    # Convert Decimal types to float for JSON serialization
    # DynamoDB returns Decimal objects which JSON cannot serialize by default
    for item in items:
        for k, v in item.items():
            if isinstance(v, Decimal):
                item[k] = float(v)

    # Return up to 200 most recent transactions
    # This limits response size and provides the most useful data (recent changes)
    # Note: items are already sorted newest-first from GSI query
    return response(200, items[:200])

def response(status_code, body):
    """
    Helper function to format Lambda response with consistent headers and CORS.

    Args:
        status_code: HTTP status code
        body: Dictionary to be JSON-encoded (or empty string for OPTIONS)

    Returns: API Gateway Lambda Proxy Integration response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': CORS_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,x-api-key,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,GET'
        },
        'body': json.dumps(body) if body else ''
    }
