import json
import os
import boto3
from boto3.dynamodb.conditions import Attr

# Initialize DynamoDB with inventory table
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'InventoryIQ'))
CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '*')

def lambda_handler(event, _context):
    """
    Deletes a category by reassigning all items in that category to "Uncategorized".

    Flow:
    1. Handle CORS preflight OPTIONS request
    2. Extract verified userID from X-Verified-UserID header (injected by Proxy.py)
    3. Return 401 if userID is missing (authentication requirement)
    4. Extract categoryName from URL path
    5. Prevent deletion of "Uncategorized" category (system requirement)
    6. Scan for all items with matching category and verified userID
    7. Update each item: set category to "Uncategorized"
    8. Return count of items updated

    Auth: X-Verified-UserID header (verified by Proxy.py after JWT validation)

    URL Path:
    - categoryName: Required. Category name to delete (extracted from path)

    Response: {'itemsUpdated': N} where N is number of items reassigned

    Design Note: "Uncategorized" is not actually deleted, items are reassigned to it.
    This prevents orphaned items and ensures no data loss.
    """
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return response(200, '')

    # Extract verified userID from header (injected by Proxy.py after JWT validation)
    user_id = event.get('headers', {}).get('x-verified-userid', '').strip()
    if not user_id:
        return response(401, {'error': 'Missing or invalid authorization'})

    # Extract categoryName from URL path
    category_name = (event.get('pathParameters') or {}).get('categoryName', '')

    # Validate required fields
    if not category_name:
        return response(400, {'error': 'categoryName required'})

    # Prevent deletion of the "Uncategorized" category
    # This is a system category that must always exist as a fallback
    if category_name.lower() == 'uncategorized':
        return response(400, {'error': 'Cannot delete Uncategorized'})

    # Scan for all items with this specific category and userID
    # Use compound filter: must match BOTH userID (for multi-tenancy) AND category
    result = table.scan(
        FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
    )
    items = result.get('Items', [])

    # Pagination loop: handle DynamoDB scan limit (1MB per request)
    while 'LastEvaluatedKey' in result:
        result = table.scan(
            ExclusiveStartKey=result['LastEvaluatedKey'],
            FilterExpression=Attr('userID').eq(user_id) & Attr('category').eq(category_name)
        )
        items.extend(result.get('Items', []))

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
    return response(200, {'itemsUpdated': items_updated})

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
            'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
        },
        'body': json.dumps(body) if body else ''
    }
