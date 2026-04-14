import json
import os
import boto3
from boto3.dynamodb.conditions import Attr
from decimal import Decimal

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
    - userID: Required. Email of user to filter transactions by.

    Response: Array of transaction objects sorted newest-first, max 200 items

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

    # Extract and validate userID
    user_id = (event.get('queryStringParameters') or {}).get('userID', '')
    if not user_id:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID required'})}

    # Scan transactions table filtering by userID
    # DynamoDB scan returns max 1MB per request, so handle pagination
    result = table.scan(FilterExpression=Attr('userID').eq(user_id))
    items = result.get('Items', [])

    # Pagination loop: continue scanning if more results exist (LastEvaluatedKey present)
    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id)
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

    # Return up to 200 most recent transactions
    # This limits response size and provides the most useful data (recent changes)
    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(items[:200])}
