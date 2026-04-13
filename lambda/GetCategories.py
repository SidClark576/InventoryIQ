import json
import os
import boto3
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB with inventory table
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Retrieves all unique categories for a user's inventory items.

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Extract verified userID from X-Verified-UserID header (injected by Proxy.py)
    3. Return 401 if userID is missing (authentication requirement)
    4. Scan inventory items filtering by userID
    5. Extract unique category values from all items
    6. Sort alphabetically
    7. Ensure "Uncategorized" is always included (even if no items have it)
    8. Return sorted list of category strings

    Auth: X-Verified-UserID header (verified by Proxy.py after JWT validation)

    Response: Array of category strings, always includes "Uncategorized"

    Note: "Uncategorized" is always returned because:
    1. It's the default category for new items
    2. Users can move items to it when deleting a category
    3. Ensures UI always has at least one category option
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
    # This scans only items belonging to this user, not entire table
    result = table.query(
        IndexName='userID-index',
        KeyConditionExpression=Key('userID').eq(user_id)
    )
    items = result.get('Items', [])

    # Pagination loop: handle DynamoDB query limit (1MB per request)
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

    return response(200, categories)

def response(status_code, body):
    """
    Helper function to format Lambda response with consistent headers and CORS.

    Args:
        status_code: HTTP status code
        body: Dictionary/list to be JSON-encoded (or empty string for OPTIONS)

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
