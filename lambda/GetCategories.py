import json
import os
import boto3
from boto3.dynamodb.conditions import Key
import time as _time
import _logging

FUNCTION_NAME = 'GetCategories'

# Initialize DynamoDB with inventory table
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))

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


def _handle(event, context):
    """
    Retrieves all unique categories for a user's inventory items.

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Extract and validate userID from query parameters
    3. Scan inventory items filtering by userID
    4. Extract unique category values from all items
    5. Sort alphabetically
    6. Ensure "Uncategorized" is always included (even if no items have it)
    7. Return sorted list of category strings

    Query Parameters:
    - userID: Required. Email of user to get categories for.

    Response: Array of category strings, always includes "Uncategorized"

    Note: "Uncategorized" is always returned because:
    1. It's the default category for new items
    2. Users can move items to it when deleting a category
    3. Ensures UI always has at least one category option
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    # Extract and validate userID from securely injected headers
    headers = event.get('headers') or {}
    user_id = (headers.get('x-iq-user') or headers.get('X-Iq-User') or '').strip()
    if not user_id:
        return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'userID required'})}

    try:
        # Query userID-index GSI instead of scanning the full table
        result = table.query(
            IndexName='userID-index',
            KeyConditionExpression=Key('userID').eq(user_id)
        )
        items = result.get('Items', [])

        # Pagination loop: handle DynamoDB query page limit (1MB per request)
        while 'LastEvaluatedKey' in result:
            result = table.query(
                IndexName='userID-index',
                KeyConditionExpression=Key('userID').eq(user_id),
                ExclusiveStartKey=result['LastEvaluatedKey']
            )
            items.extend(result.get('Items', []))

        # Extract unique categories from all items
        # Set() removes duplicates, sorted() orders alphabetically
        categories = sorted(list(set(
            item.get('category', 'Uncategorized')
            for item in items
            if item.get('category')  # Filter out None/empty values
        )))

        # Always include "Uncategorized" even if user has no items with that category
        # This ensures the dropdown always has at least one option
        # and prevents errors when no items exist for that category explicitly
        if 'Uncategorized' not in categories:
            categories.append('Uncategorized')
            categories.sort()

        return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(categories)}

    except Exception as e:
        return {'statusCode': 500, 'headers': CORS, 'body': json.dumps({'error': 'Internal Server Error'})}
